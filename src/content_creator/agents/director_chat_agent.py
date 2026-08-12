from content_creator.schemas import Storyboard
from content_creator.services.llm.router import get_agent_provider
from content_creator.services.llm.validator import validate_storyboard_json

def revise_storyboard(storyboard: Storyboard, instruction: str) -> Storyboard:
    provider = get_agent_provider("chat")
    if provider.model_name != "mock":
        prompt = "Return only Storyboard JSON. Keep motion static. Do not emit code, TSX, cover, crop, scaleX or scaleY. Current storyboard: " + storyboard.model_dump_json() + " User instruction: " + instruction
        return validate_storyboard_json(provider.complete(prompt), storyboard)
    lowered = instruction.lower()
    if "third" in lowered or "第三" in instruction:
        index = 2
        if len(storyboard.scenes) > index:
            scene = storyboard.scenes[index]
            multiplier = 2 if any(word in lowered for word in ("increase", "longer", "增加")) else 1
            return storyboard.model_copy(update={"scenes":[*storyboard.scenes[:index], scene.model_copy(update={"duration_frames":scene.duration_frames * multiplier}), *storyboard.scenes[index + 1:]]})
    return storyboard
