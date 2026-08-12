import argparse
import json
from pathlib import Path
from content_creator.agents.director_chat_agent import revise_storyboard
from content_creator.schemas import ScenePlan, Storyboard

def main() -> None:
    parser = argparse.ArgumentParser(description="Local Director Chat Mode")
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    project_dir = Path(args.project)
    data = json.loads((project_dir / "render_data.json").read_text(encoding="utf-8"))
    scenes = [ScenePlan(scene_id=f"{index + 1:03d}", asset_id=item["asset_id"], duration_frames=item["duration_frames"], transition=item["transition"]) for index, item in enumerate(data["timeline"])]
    storyboard = Storyboard(scenes=scenes)
    print(f"Director Chat: {len(scenes)} scenes")
    while True:
        instruction = input("> ").strip()
        if instruction.lower() in {"exit", "quit"}: break
        storyboard = revise_storyboard(storyboard, instruction)
        print(storyboard.model_dump_json(indent=2))

if __name__ == "__main__": main()
