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
