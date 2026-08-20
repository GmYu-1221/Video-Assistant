from types import SimpleNamespace

from content_creator.services.source_pipeline import _article_selection_succeeded, _asset_preview_failure_details


def test_article_selection_accepts_successful_retry_with_historical_errors():
    diagnostics = {
        "agent_mode": "retry_success",
        "fallback": False,
        "selected_candidate_ids": ["text-000"],
        "agent_errors": ["JSONDecodeError: invalid first response"],
    }

    assert _article_selection_succeeded(diagnostics)


def test_article_selection_rejects_fallback_or_incomplete_state():
    assert not _article_selection_succeeded(
        {"agent_mode": "deterministic_fallback", "fallback": True}
    )
    assert not _article_selection_succeeded(
        {"agent_mode": "retry_success", "fallback": True}
    )
    assert not _article_selection_succeeded(
        {"agent_mode": "deterministic_fallback", "fallback": False}
    )


def test_article_selection_accepts_first_attempt_success():
    assert _article_selection_succeeded(
        {"agent_mode": "success", "fallback": False, "agent_errors": []}
    )


def test_asset_preview_failure_preserves_batch_contract_path_and_unverified_ids():
    details = _asset_preview_failure_details(
        {"batches": [{
            "batch": 2,
            "error": "asset_visual_batch-002 validation failed: candidate_profiles.0.headline_bbox: invalid bbox",
        }]},
        {"asset-003", "asset-004"},
        {"asset-003": SimpleNamespace(analysis_status="fallback")},
    )
    assert details == [
        "batch 2: asset_visual_batch-002 validation failed: candidate_profiles.0.headline_bbox: invalid bbox",
        "unverified asset_ids: asset-003, asset-004",
    ]
