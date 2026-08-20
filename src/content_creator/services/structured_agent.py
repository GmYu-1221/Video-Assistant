"""One strict JSON contract for every structured Agent call."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Generic, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)
JsonPath = tuple[str | int, ...]


@dataclass(frozen=True)
class ValidationIssue:
    path: JsonPath
    code: str
    message: str
    related_paths: tuple[JsonPath, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "path": _path_text(self.path), "code": self.code, "message": self.message,
            "related_paths": [_path_text(path) for path in self.related_paths],
        }


SemanticValidator = Callable[[T], list[ValidationIssue]]


class StructuredAgentValidationError(ValueError):
    def __init__(self, contract_name: str, issues: list[ValidationIssue]):
        self.contract_name = contract_name
        self.issues = issues
        detail = "; ".join(f"{_path_text(issue.path)}: {issue.message}" for issue in issues[:8])
        super().__init__(f"{contract_name} validation failed: {detail}")


class StructuredAgentRunner(Generic[T]):
    def run(
        self,
        *,
        provider,
        contract_name: str,
        prompt: dict,
        schema: type[T],
        artifact_dir: str | Path,
        semantic_validator: SemanticValidator[T] | None = None,
        image_paths: list[str] | None = None,
    ) -> T:
        run_dir = Path(artifact_dir) / "agent_runs" / contract_name
        run_dir.mkdir(parents=True, exist_ok=True)
        schema_json = schema.model_json_schema(mode="validation")
        initial_prompt = _contract_prompt(prompt, schema_json)
        attempts: list[dict] = []
        try:
            raw = self._invoke(provider, initial_prompt, schema_json, contract_name, image_paths)
        except Exception as exc:
            attempts.append({"attempt": 1, "status": "invocation_failed", "issues": [{"path": "$", "code": "provider_error", "message": f"{type(exc).__name__}: {exc}", "related_paths": []}]})
            self._write_validation(run_dir, "invocation_failed", attempts)
            raise
        _atomic_text(run_dir / "attempt-1.txt", raw)
        model, issues, parsed = self._validate(raw, schema, semantic_validator)
        attempts.append({"attempt": 1, "status": "passed" if not issues else "failed", "issues": [item.as_dict() for item in issues]})
        if not issues:
            self._write_validation(run_dir, "passed", attempts)
            return model  # type: ignore[return-value]

        mutable_paths = _mutable_paths(issues)
        locked = _locked_leaves(parsed, mutable_paths) if parsed is not None else {}
        repair_prompt = _repair_prompt(prompt, schema_json, raw, issues)
        try:
            repaired_raw = self._invoke(provider, repair_prompt, schema_json, contract_name, image_paths)
        except Exception as exc:
            attempts.append({"attempt": 2, "status": "invocation_failed", "issues": [{"path": "$", "code": "provider_error", "message": f"{type(exc).__name__}: {exc}", "related_paths": []}]})
            self._write_validation(run_dir, "invocation_failed", attempts)
            raise
        _atomic_text(run_dir / "attempt-2.txt", repaired_raw)
        repaired, repair_issues, repaired_parsed = self._validate(repaired_raw, schema, semantic_validator)
        if repaired_parsed is not None:
            changes = _locked_changes(locked, repaired_parsed)
            if parsed is not None:
                changes.extend(_structural_changes(parsed, repaired_parsed, mutable_paths))
                changes = list(dict.fromkeys(changes))
            if changes:
                repair_issues.extend(ValidationIssue(
                    path=path, code="repair_changed_legal_field",
                    message="schema repair changed a field outside error_paths/related_paths",
                ) for path in changes[:20])
        attempts.append({"attempt": 2, "status": "passed" if not repair_issues else "failed", "issues": [item.as_dict() for item in repair_issues]})
        if repair_issues:
            self._write_validation(run_dir, "failed", attempts)
            raise StructuredAgentValidationError(contract_name, repair_issues)
        self._write_validation(run_dir, "passed_after_repair", attempts)
        return repaired  # type: ignore[return-value]

    @staticmethod
    def _invoke(provider, prompt: str, schema: dict, name: str, image_paths: list[str] | None) -> str:
        if image_paths is not None:
            method = getattr(provider, "complete_multimodal_structured", None)
            if callable(method):
                return method(prompt, image_paths, schema, name)
            return provider.complete_multimodal(prompt, image_paths)
        method = getattr(provider, "complete_structured", None)
        if callable(method):
            return method(prompt, schema, name)
        return provider.complete_json(prompt)

    @staticmethod
    def _validate(raw: str, schema: type[T], semantic_validator: SemanticValidator[T] | None):
        parsed, envelope_issue = _strict_json_object(raw)
        if envelope_issue:
            return None, [envelope_issue], parsed
        try:
            model = schema.model_validate_json(raw.strip(), strict=True)
        except ValidationError as exc:
            issues = [ValidationIssue(tuple(error["loc"]), str(error["type"]), error["msg"]) for error in exc.errors(include_url=False, include_input=False)]
            return None, issues, parsed
        issues = semantic_validator(model) if semantic_validator else []
        return model, issues, parsed

    @staticmethod
    def _write_validation(run_dir: Path, status: str, attempts: list[dict]) -> None:
        payload = {"status": status, "attempts": attempts}
        if status in {"failed", "invocation_failed"} and attempts:
            payload["error"] = "; ".join(
                f"{item['path']}: {item['message']}" for item in attempts[-1].get("issues", [])[:8]
            )
        _atomic_text(run_dir / "validation.json", json.dumps(payload, ensure_ascii=False, indent=2))


def _contract_prompt(prompt: dict, schema: dict) -> str:
    return json.dumps(prompt | {"agent_output_contract": {
        "format": "Return exactly one JSON object and nothing else.",
        "markdown_fence": "forbidden", "explanation_text": "forbidden",
        "required_fields": "Every schema-required field must be present.",
        "extra_fields": "forbidden", "output_schema": schema,
    }}, ensure_ascii=False)


def _repair_prompt(prompt: dict, schema: dict, raw: str, issues: list[ValidationIssue]) -> str:
    return json.dumps({
        "task": "Repair the previous response to satisfy the schema. Return exactly one JSON object.",
        "original_task": prompt,
        "previous_response": raw,
        "validation_errors": [issue.as_dict() for issue in issues],
        "repair_rules": [
            "Only change error_paths and explicitly listed related_paths.",
            "Preserve every other already-valid value, array item, decision, and ordering exactly.",
            "Do not redesign content, scene structure, duration, weights, selections, or references unless that exact path is invalid.",
            "Do not use Markdown fences or explanation text.",
        ],
        "output_schema": schema,
    }, ensure_ascii=False)


def issue(path: JsonPath, code: str, message: str, *, related_paths: tuple[JsonPath, ...] = ()) -> ValidationIssue:
    return ValidationIssue(path, code, message, related_paths)


def _strict_json_object(raw: str) -> tuple[dict | None, ValidationIssue | None]:
    stripped = raw.strip()
    if not stripped:
        return None, ValidationIssue((), "empty_response", "response is empty")
    if stripped.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped, flags=re.I).strip()
        return _try_object(cleaned), ValidationIssue((), "markdown_fence", "Markdown fences are forbidden")
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        candidate = _embedded_object(stripped)
        return candidate, ValidationIssue((), "invalid_json_envelope", f"response must contain only one JSON object: {exc.msg}")
    if not isinstance(value, dict):
        return None, ValidationIssue((), "not_object", "response must be a JSON object")
    return value, None


def _try_object(value: str) -> dict | None:
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _embedded_object(value: str) -> dict | None:
    start = value.find("{")
    if start < 0:
        return None
    try:
        parsed, _ = json.JSONDecoder().raw_decode(value[start:])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _mutable_paths(issues: list[ValidationIssue]) -> set[JsonPath]:
    return {path for item in issues for path in (item.path, *item.related_paths) if path}


def _locked_leaves(value, mutable: set[JsonPath], path: JsonPath = ()) -> dict[JsonPath, object]:
    locked: dict[JsonPath, object] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            locked.update(_locked_leaves(child, mutable, path + (key,)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            locked.update(_locked_leaves(child, mutable, path + (index,)))
    elif not any(_paths_overlap(path, allowed) for allowed in mutable):
        locked[path] = value
    return locked


def _paths_overlap(left: JsonPath, right: JsonPath) -> bool:
    length = min(len(left), len(right))
    return left[:length] == right[:length]


def _locked_changes(locked: dict[JsonPath, object], repaired: dict) -> list[JsonPath]:
    changed = []
    for path, expected in locked.items():
        present, actual = _at_path(repaired, path)
        if not present or actual != expected:
            changed.append(path)
    return changed


def _structural_changes(original, repaired, mutable: set[JsonPath], path: JsonPath = ()) -> list[JsonPath]:
    changed: list[JsonPath] = []
    if isinstance(original, dict):
        if not isinstance(repaired, dict):
            return [] if any(_paths_overlap(path, allowed) for allowed in mutable) else [path]
        original_keys, repaired_keys = set(original), set(repaired)
        for key in original_keys - repaired_keys:
            child = path + (key,)
            if not any(_paths_overlap(child, allowed) for allowed in mutable):
                changed.append(child)
        for key in repaired_keys - original_keys:
            child = path + (key,)
            if not any(_paths_overlap(child, allowed) for allowed in mutable):
                changed.append(child)
        for key in original_keys & repaired_keys:
            changed.extend(_structural_changes(original[key], repaired[key], mutable, path + (key,)))
    elif isinstance(original, list):
        if not isinstance(repaired, list):
            return [] if any(_paths_overlap(path, allowed) for allowed in mutable) else [path]
        length_change_allowed = any(
            allowed[:len(path)] == path and (
                len(allowed) == len(path)
                or (len(allowed) > len(path) and isinstance(allowed[len(path)], str) and allowed[len(path)].startswith("missing-"))
            )
            for allowed in mutable
        )
        if len(original) != len(repaired) and not length_change_allowed:
            changed.append(path)
        for index in range(min(len(original), len(repaired))):
            changed.extend(_structural_changes(original[index], repaired[index], mutable, path + (index,)))
    return changed


def _at_path(value, path: JsonPath) -> tuple[bool, object]:
    current = value
    for part in path:
        try:
            current = current[part]
        except (KeyError, IndexError, TypeError):
            return False, None
    return True, current


def _path_text(path: JsonPath) -> str:
    return ".".join(map(str, path)) if path else "$"


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)
