from content_creator.services.source_pipeline import _article_selection_succeeded


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
