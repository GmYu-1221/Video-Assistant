from pathlib import Path
from content_creator.schemas import RemotionAdvice

_SKILL_NAMES = ("remotion-best-practices", "remotion-docs", "remotion-markup", "remotion-render")

def _skill_root() -> Path:
    return Path(__file__).resolve().parents[3] / ".agents" / "skills"

def load_skill_documents() -> tuple[str, ...]:
    root = _skill_root()
    documents = tuple(str(root / name / "SKILL.md") for name in _SKILL_NAMES if (root / name / "SKILL.md").is_file())
    if not documents:
        raise RuntimeError("official Remotion skills are not installed under .agents/skills")
    return documents

def build_advice(state: dict) -> RemotionAdvice:
    storyboard = state["storyboard"]
    if any(scene.motion.type != "static" for scene in storyboard.scenes):
        raise ValueError("Remotion Agent requires static motion unless explicitly approved by a future policy")
    return RemotionAdvice(skill_documents=load_skill_documents())

def remotion_node(state: dict) -> dict:
    advice = build_advice(state)
    return {"remotion_advice": advice}
