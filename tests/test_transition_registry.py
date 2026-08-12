from content_creator.schemas import PRESETS, TransitionPolicy, TransitionType
from content_creator.services.timeline.slideshow_builder import REAL_TRANSITIONS, _choose_types

def test_new_transition_types_and_presets_are_real():
    assert {TransitionType.clock_wipe, TransitionType.blinds, TransitionType.pixel_reveal} <= REAL_TRANSITIONS
    assert all(item in REAL_TRANSITIONS for preset in PRESETS.values() for item in preset)
    assert TransitionType.black_flash in REAL_TRANSITIONS

def test_selector_filters_fallbacks_and_cools_down_complexity():
    policy = TransitionPolicy(mode='random', allowed=[TransitionType.glitch, TransitionType.zoom_cut, TransitionType.fade], seed=12)
    selected = _choose_types(12, policy)
    assert TransitionType.zoom_cut not in selected
    assert selected == _choose_types(12, policy)
    assert all(not (a is TransitionType.glitch and b is TransitionType.glitch) for a, b in zip(selected, selected[1:]))
