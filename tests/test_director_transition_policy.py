from content_creator.schemas import DirectorPlan
from content_creator.services.director.transition_policy import apply_transition_policy, build_transition_sequence


def test_transition_sequence_is_reproducible_and_varied():
    first = build_transition_sequence(8, [0.1] * 8, seed=7)
    second = build_transition_sequence(8, [0.1] * 8, seed=7)
    assert first == second
    assert len(set(first)) >= 4


def test_policy_repairs_fade_overuse_and_triples():
    plan = DirectorPlan.model_validate({"timeline": [
        {"asset_id": f"a{i}", "duration_frames": 60, "transition": {"type": "fade", "duration_frames": 15}, "motion": "static", "reason": "test"}
        for i in range(8)
    ]})
    repaired = apply_transition_policy(plan, [0.2, 0.2, 0.8, 0.8, 0.2, 0.8, 0.2, 0.8])
    transitions = [item.transition.type.value for item in repaired.timeline]
    assert len(set(transitions)) >= 4
    assert all(not (a == b == c) for a, b, c in zip(transitions, transitions[1:], transitions[2:]))
    assert transitions.count("fade") / len(transitions) < 0.30
    assert all(item.transition.duration_frames <= 8 for item in repaired.timeline)
