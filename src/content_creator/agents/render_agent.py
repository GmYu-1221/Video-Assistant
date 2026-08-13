import json
import logging
from pathlib import Path
from content_creator.schemas import AnimationEffect, AnimationEffectType, DirectorPlan, DirectorTimelineItem, TimelineItem, RemotionCreativePlan, VisualEvent, VideoProject, TransitionEffectPlanItem, TransitionEffectType
from content_creator.agents.remotion_agent import create_remotion_creative_plan
from content_creator.services.music import adapt_audio_to_duration

logger = logging.getLogger(__name__)

def compile_render_plan(project: VideoProject, storyboard, creative_plan: RemotionCreativePlan | None = None, animation_plan=None, transition_effect_plan=None) -> VideoProject:
    cursor = 0
    timeline = []
    legacy_animation_by_asset = {}
    legacy_transition_by_source = {}
    if creative_plan is not None and not isinstance(creative_plan, RemotionCreativePlan):
        # Legacy positional AnimationPlan/TransitionEffectPlan callers.
        legacy_animation = creative_plan
        legacy_transition = animation_plan if transition_effect_plan is None else transition_effect_plan
        legacy_animation_by_asset = {x.asset_id: x for x in getattr(legacy_animation, "animations", [])}
        legacy_transition_by_source = {x.from_asset_id: x for x in getattr(legacy_transition, "transitions", [])}
        plans = []
        for scene in storyboard.scenes:
            events = []
            animation = next((x for x in getattr(legacy_animation, "animations", []) if x.asset_id == scene.asset_id), None)
            if animation:
                events.append(VisualEvent(type=animation.type.value, phase="entrance", start_frame=0, duration_frames=animation.duration_frames, params=animation.params))
            transition = next((x for x in getattr(legacy_transition, "transitions", []) if x.from_asset_id == scene.asset_id), None)
            if transition:
                events.append(VisualEvent(type=transition.type.value, phase="transition", start_frame=max(0, scene.duration_frames-transition.duration_frames), duration_frames=transition.duration_frames, source_asset_id=transition.from_asset_id, target_asset_id=transition.to_asset_id, params=transition.params))
            plans.append({"scene_id": scene.asset_id, "visual_events": events})
        creative_plan = RemotionCreativePlan.model_validate({"plans": plans})
    if creative_plan is None:
        # Storyboard is a durable plan boundary. Rebuild a compatible DirectorPlan
        # so animations survive callers that compile a storyboard directly.
        rebuilt_plan = DirectorPlan(timeline=[DirectorTimelineItem(asset_id=scene.asset_id, duration_frames=scene.duration_frames, transition=scene.transition, motion=scene.motion.type, reason=scene.emotion, creative_intent=scene.creative_intent, transition_intent=scene.transition_intent, timing=scene.timing) for scene in storyboard.scenes])
        # Legacy callers that do not pass an explicit plan retain the old API
        # conversion while the production entry points use the unified plan.
        from content_creator.agents.remotion_agent import create_remotion_plans
        generated_animation, generated_transitions = create_remotion_plans(rebuilt_plan)
        legacy_animation_by_asset = {x.asset_id: x for x in generated_animation.animations}
        legacy_transition_by_source = {x.from_asset_id: x for x in generated_transitions.transitions}
        creative_plan = RemotionCreativePlan(plans=[])
    events_by_scene = {item.scene_id: item.visual_events for item in creative_plan.plans}
    for scene in storyboard.scenes:
        end = cursor + scene.duration_frames
        events = events_by_scene.get(scene.asset_id, [])
        for event in events:
            if event.phase == "entrance":
                event_end = event.start_frame + event.duration_frames
                logger.info(
                    "Entrance event:\n%s\nframes %d-%d\nStatic hold:\nframes %d-%d",
                    event.type,
                    event.start_frame,
                    event_end,
                    event_end,
                    scene.duration_frames,
                )
        entrance = next((event for event in events if event.phase in {"entrance", "effect"}), None)
        transition_event = next((event for event in events if event.phase == "transition"), None)
        legacy_animation = legacy_animation_by_asset.get(scene.asset_id)
        if legacy_animation is None and entrance and entrance.type in {item.value for item in AnimationEffectType}:
            legacy_animation = AnimationEffect(asset_id=scene.asset_id, type=AnimationEffectType(entrance.type), component=entrance.type, duration_frames=entrance.duration_frames, params=entrance.params)
        legacy_transition = legacy_transition_by_source.get(scene.asset_id)
        if legacy_transition is None and transition_event and transition_event.type in {item.value for item in TransitionEffectType} and transition_event.target_asset_id:
            legacy_transition = TransitionEffectPlanItem(from_asset_id=transition_event.source_asset_id or scene.asset_id, to_asset_id=transition_event.target_asset_id, type=TransitionEffectType(transition_event.type), duration_frames=transition_event.duration_frames, params=transition_event.params)
        timeline.append(TimelineItem(asset_id=scene.asset_id, start_frame=cursor, end_frame=end, duration_frames=scene.duration_frames, transition=scene.transition, animation=legacy_animation, transition_effect=legacy_transition, visual_events=events))
        cursor = end
    project_dir = Path(project.output.project_dir).resolve()
    audio_dir = project_dir / "audio"
    if not audio_dir.is_dir():
        raise RuntimeError(f"Project audio directory does not exist: {audio_dir}")
    audio_path = audio_dir / "bgm_adapted.wav"
    source_relative = project.audio.source_path
    if not source_relative:
        raise RuntimeError("Project audio source_path is missing; cannot adapt BGM safely")
    source_audio = (project_dir / source_relative).resolve()
    if not source_audio.is_file() or source_audio.parent != audio_dir:
        raise RuntimeError(f"Project source audio does not exist inside audio directory: {source_audio}")
    adapt_audio_to_duration(source_audio, cursor / project.fps, audio_path)
    updated = project.model_copy(update={"timeline": timeline, "audio": project.audio.model_copy(update={"path":"audio/bgm_adapted.wav", "duration": cursor / project.fps, "sample_rate":44100})})
    payload = updated.model_dump(mode="json")
    payload["output"] = {"project_dir":".", "render_data":"render_data.json", "final_video":"render/final.mp4"}
    Path(updated.output.render_data).resolve().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return updated

def render_node(state: dict) -> dict:
    project = compile_render_plan(state["project"], state["storyboard"], state.get("remotion_creative_plan"))
    return {"project": project, "render_plan": project.model_dump(mode="json")}
