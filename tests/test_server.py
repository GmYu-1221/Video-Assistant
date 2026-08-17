from urllib.request import Request, urlopen
from content_creator.services.server import MediaServer

def test_server_serves_only_project_media(tmp_path):
    (tmp_path/'materials').mkdir(); (tmp_path/'materials/a.jpg').write_bytes(b'a')
    server=MediaServer(tmp_path); base=server.start()
    try:
        assert urlopen(base+'/materials/a.jpg').read()==b'a'
        try: urlopen(base+'/../etc/passwd')
        except Exception: pass
    finally: server.close()


def test_server_supports_cors_and_ranges_for_background_video(tmp_path):
    (tmp_path / 'background').mkdir()
    (tmp_path / 'background' / 'background.mp4').write_bytes(b'0123456789')
    server = MediaServer(tmp_path)
    base = server.start()
    try:
        response = urlopen(Request(base + '/background/background.mp4', headers={'Range': 'bytes=2-5'}))
        assert response.status == 206
        assert response.read() == b'2345'
        assert response.headers['Content-Range'] == 'bytes 2-5/10'
        assert response.headers['Access-Control-Allow-Origin'] == '*'
        head = urlopen(Request(base + '/background/background.mp4', method='HEAD'))
        assert head.headers['Accept-Ranges'] == 'bytes'
        assert head.headers['Content-Type'] == 'video/mp4'
    finally:
        server.close()
