from content_creator.web import create_app


def test_web_app_exposes_single_url_job_api(tmp_path):
    app = create_app(tmp_path)
    routes = {route.path for route in app.routes}
    assert "/api/jobs" in routes
    assert "/api/jobs/{job_id}" in routes
    assert "/api/jobs/{job_id}/events" in routes
    assert "/api/jobs/{job_id}/video" in routes
