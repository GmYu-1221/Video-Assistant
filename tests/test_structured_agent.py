import json

import pytest
from pydantic import Field

from content_creator.schemas import StrictAgentModel
from content_creator.services.structured_agent import StructuredAgentRunner, StructuredAgentValidationError, issue


class Decision(StrictAgentModel):
    choice: str = Field(min_length=1)
    score: int = Field(ge=1, le=10)


class Item(StrictAgentModel):
    name: str
    score: int


class ListDecision(StrictAgentModel):
    items: list[Item]


class Provider:
    model_name = "test"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def complete_json(self, _prompt):
        self.calls += 1
        return next(self.responses)


def test_fenced_json_requires_one_repair_and_preserves_payload(tmp_path):
    provider = Provider(['```json\n{"choice":"a","score":3}\n```', '{"choice":"a","score":3}'])
    result = StructuredAgentRunner().run(
        provider=provider, contract_name="decision", prompt={"task": "choose"},
        schema=Decision, artifact_dir=tmp_path,
    )
    assert result == Decision(choice="a", score=3)
    assert provider.calls == 2
    validation = json.loads((tmp_path / "agent_runs" / "decision" / "validation.json").read_text())
    assert validation["status"] == "passed_after_repair"
    assert validation["attempts"][0]["issues"][0]["code"] == "markdown_fence"


def test_repair_cannot_change_valid_field(tmp_path):
    provider = Provider(['{"choice":"a"}', '{"choice":"b","score":3}'])
    with pytest.raises(StructuredAgentValidationError, match="outside error_paths"):
        StructuredAgentRunner().run(
            provider=provider, contract_name="decision", prompt={"task": "choose"},
            schema=Decision, artifact_dir=tmp_path,
        )


def test_related_paths_explicitly_allow_associated_change(tmp_path):
    provider = Provider(['{"choice":"a","score":3}', '{"choice":"b","score":3}'])

    def validate(value):
        return [] if value.choice == "b" else [issue(("business_rule",), "bad_choice", "choice must be b", related_paths=(("choice",),))]

    result = StructuredAgentRunner().run(
        provider=provider, contract_name="decision", prompt={"task": "choose"},
        schema=Decision, artifact_dir=tmp_path, semantic_validator=validate,
    )
    assert result.choice == "b"


def test_second_invalid_response_fails_and_saves_both_attempts(tmp_path):
    provider = Provider(['{"choice":"a"}', '{"choice":"a"}'])
    with pytest.raises(StructuredAgentValidationError):
        StructuredAgentRunner().run(
            provider=provider, contract_name="decision", prompt={"task": "choose"},
            schema=Decision, artifact_dir=tmp_path,
        )
    run_dir = tmp_path / "agent_runs" / "decision"
    assert (run_dir / "attempt-1.txt").is_file()
    assert (run_dir / "attempt-2.txt").is_file()
    validation = json.loads((run_dir / "validation.json").read_text())
    assert validation["status"] == "failed"
    assert "score" in validation["error"]


def test_repair_cannot_append_unrelated_array_item_while_fixing_field(tmp_path):
    provider = Provider([
        '{"items":[{"name":"a"}]}',
        '{"items":[{"name":"a","score":3},{"name":"new","score":4}]}',
    ])
    with pytest.raises(StructuredAgentValidationError, match="outside error_paths"):
        StructuredAgentRunner().run(
            provider=provider, contract_name="list", prompt={"task": "list"},
            schema=ListDecision, artifact_dir=tmp_path,
        )


def test_provider_error_is_not_repaired_and_writes_validation(tmp_path):
    class FailedProvider:
        calls = 0
        def complete_json(self, _prompt):
            self.calls += 1
            raise TimeoutError("gateway timeout")

    provider = FailedProvider()
    with pytest.raises(TimeoutError):
        StructuredAgentRunner().run(
            provider=provider, contract_name="decision", prompt={"task": "choose"},
            schema=Decision, artifact_dir=tmp_path,
        )
    assert provider.calls == 1
    validation = json.loads((tmp_path / "agent_runs" / "decision" / "validation.json").read_text())
    assert validation["status"] == "invocation_failed"
    assert validation["attempts"][0]["issues"][0]["code"] == "provider_error"
