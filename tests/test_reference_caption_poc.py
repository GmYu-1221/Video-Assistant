import json

import pytest

from content_creator.services.renderer.reference_caption_poc import build_poc_props, validate_layout_audit


def test_build_poc_props_uses_frozen_project_copy(tmp_path):
    project = tmp_path / "project"
    media = project / "materials/processed/image.jpg"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"image")
    (project / "render_data.json").write_text(json.dumps({
        "persistent_title": {"content": "测试项目：三段式标题 - 作者 - 博客园"},
        "images": [{"relative_path": "materials/processed/image.jpg", "semantic_profile": {"embedded_headline_text": "图片内标题"}}],
        "timeline": [{"narrative": {"contents": [{"short": "冻结短文案", "full": "冻结完整文案。"}]}}],
    }), encoding="utf-8")
    (project / "viral_copy_plan.json").write_text(json.dumps({"content_units": [
        {"full": "第一段冻结说明。"}, {"full": "第二段冻结说明。"}, {"full": "问题？"},
    ]}), encoding="utf-8")
    background = tmp_path / "background.mp4"
    background.write_bytes(b"video")

    props = build_poc_props(project, background, "http://127.0.0.1:9999", tmp_path)

    assert props["topLines"] == ["测试项目", "三段式标题", "冻结短文案"]
    assert props["summary"] == "第一段冻结说明。第二段冻结说明。"
    assert props["mediaUrl"].endswith("/project/materials/processed/image.jpg")
    assert props["backgroundVideoUrl"].endswith("/background.mp4")


def test_layout_audit_rejects_overflow():
    geometry = {
        "top-primary": (60, 92, 960, 96),
        "top-secondary": (60, 210, 960, 108),
        "top-tertiary": (60, 352, 960, 84),
        "media": (0, 655, 1080, 610),
        "summary": (80, 1325, 920, 500),
    }
    blocks = [{
        "id": block_id, "x": values[0], "y": values[1], "width": values[2], "height": values[3],
        "scrollWidth": values[2], "clientWidth": values[2], "scrollHeight": values[3], "clientHeight": values[3],
        "zIndex": "5", "effectiveZIndex": "5",
    } for block_id, values in geometry.items()]
    audit = {"templateId": "reference_caption_v1", "frame": 30, "fontsReady": True, "mediaObjectFit": "contain", "mediaObjectPosition": "50% 50%", "backgroundZIndex": "0", "blocks": blocks}
    validate_layout_audit(audit, 30)
    blocks[-1]["scrollHeight"] = 502
    with pytest.raises(ValueError, match="overflow"):
        validate_layout_audit(audit, 30)
