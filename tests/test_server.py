from urllib.request import urlopen
from content_creator.services.server import MediaServer

def test_server_serves_only_project_media(tmp_path):
    (tmp_path/'materials').mkdir(); (tmp_path/'materials/a.jpg').write_bytes(b'a')
    server=MediaServer(tmp_path); base=server.start()
    try:
        assert urlopen(base+'/materials/a.jpg').read()==b'a'
        try: urlopen(base+'/../etc/passwd')
        except Exception: pass
    finally: server.close()
