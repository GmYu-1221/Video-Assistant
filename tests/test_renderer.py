from content_creator.services.renderer import remotion

def test_renderer_closes_server_on_failure(tmp_path, monkeypatch):
    class FakeServer:
        closed=False
        def __init__(self,*a): pass
        def start(self): return 'http://127.0.0.1:1'
        def close(self): self.closed=True
    fake=FakeServer(); monkeypatch.setattr(remotion,'MediaServer',lambda *_: fake)
    monkeypatch.setattr(remotion.subprocess,'run',lambda *a,**k: type('R',(),{'returncode':1})())
    from content_creator.schemas import VideoProject
    try: remotion.render_project(VideoProject.model_construct(output=type('O',(),{'project_dir':str(tmp_path)})()),tmp_path,tmp_path/'x.mp4')
    except Exception: pass
    assert fake.closed


def test_renderer_quiet_mode_captures_remotion_output(tmp_path, monkeypatch):
    class FakeServer:
        def __init__(self, *args): pass
        def start(self): return "http://127.0.0.1:1"
        def close(self): pass

    calls = []
    target = tmp_path / "x.mp4"
    monkeypatch.setattr(remotion, "MediaServer", FakeServer)

    def fake_run(*args, **kwargs):
        calls.append(kwargs)
        target.write_bytes(b"video")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(remotion.subprocess, "run", fake_run)
    from content_creator.schemas import VideoProject
    project = VideoProject.model_construct(output=type("O", (), {"project_dir": str(tmp_path)})())
    remotion.render_project(project, tmp_path, target, quiet=True)
    assert calls == [{"cwd": tmp_path, "check": False, "capture_output": True, "text": True}]


def test_renderer_default_keeps_remotion_output_streaming(tmp_path, monkeypatch):
    class FakeServer:
        def __init__(self, *args): pass
        def start(self): return "http://127.0.0.1:1"
        def close(self): pass

    calls = []
    target = tmp_path / "x.mp4"
    monkeypatch.setattr(remotion, "MediaServer", FakeServer)

    def fake_run(*args, **kwargs):
        calls.append(kwargs)
        target.write_bytes(b"video")
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(remotion.subprocess, "run", fake_run)
    from content_creator.schemas import VideoProject
    project = VideoProject.model_construct(output=type("O", (), {"project_dir": str(tmp_path)})())
    remotion.render_project(project, tmp_path, target)
    assert calls == [{"cwd": tmp_path, "check": False, "capture_output": False, "text": False}]
