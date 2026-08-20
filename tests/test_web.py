from fastapi.testclient import TestClient

from content_creator.web import Job, _PAGE, create_app


def test_web_routes_and_removed_feedback_api(tmp_path):
    app = create_app(tmp_path)
    routes = {route.path for route in app.routes}
    assert {"/api/jobs", "/api/jobs/{job_id}", "/api/jobs/{job_id}/events", "/api/jobs/{job_id}/video", "/api/browser-import"} <= routes
    assert not any("feedback" in route for route in routes)


def test_web_ui_has_three_urls_and_new_stages():
    assert _PAGE.count('class="url"') == 3
    stages = ("文章处理", "内容编排", "导演设计", "文案适配", "导演复核", "动画生成", "视频渲染", "完成")
    for stage in stages:
        assert stage in _PAGE
    assert [(_PAGE.index(stage), stage) for stage in stages] == sorted((_PAGE.index(stage), stage) for stage in stages)
    assert "版本" not in _PAGE


def test_job_api_uses_urls_and_one_video_url(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    manager = app.state.jobs
    monkeypatch.setattr(manager, "submit", lambda urls: Job(id="job", urls=urls, status="queued"))
    client = TestClient(app)
    for count in (1, 2, 3):
        response = client.post("/api/jobs", json={"urls": [f"https://example.com/{i}" for i in range(count)]})
        assert response.status_code == 200
        assert len(response.json()["urls"]) == count
        assert "video_url" in response.json()
    assert client.post("/api/jobs", json={"urls": []}).status_code == 422
    assert client.post("/api/jobs", json={"urls": [f"https://example.com/{i}" for i in range(4)]}).status_code == 422
