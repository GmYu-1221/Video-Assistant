from pathlib import Path

from content_creator.web import Job, JobManager, _job_payload, create_app


def test_web_app_exposes_single_url_job_api(tmp_path):
    app = create_app(tmp_path)
    routes = {route.path for route in app.routes}
    assert "/api/jobs" in routes
    assert "/api/jobs/{job_id}" in routes
    assert "/api/jobs/{job_id}/events" in routes
    assert "/api/jobs/{job_id}/video" in routes
    assert "/api/browser-import" in routes
    assert "/api/browser-asset-upload" in routes


def test_browser_import_waiting_payload_and_resume(tmp_path, monkeypatch):
    manager = JobManager(tmp_path, Path.cwd())
    job = Job(id="job-1", url="https://zhuanlan.zhihu.com/p/1", status="awaiting_browser_import", browser_import_status=403, browser_import_url=manager.browser_import_url())
    with manager.lock:
        manager.jobs[job.id] = job
    payload = _job_payload(job)
    assert payload["browser_import"]["status_code"] == 403
    assert payload["browser_import"]["bookmarklet_url"].startswith("javascript:")
    monkeypatch.setattr(manager, "_run", lambda *_args, **_kwargs: None)
    resumed = manager.accept_browser_import(manager.import_token, "https://zhuanlan.zhihu.com/p/1#section", "<article><p>imported</p></article>")
    assert resumed is job
    assert job.status == "running"
