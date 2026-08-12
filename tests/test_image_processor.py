from PIL import Image
from content_creator.services.assets import scan_and_process

def test_process_images(tmp_path):
    source=tmp_path/'in'; source.mkdir(); Image.new('RGB',(3000,1000),'red').save(source/'a.png')
    assets=scan_and_process(source,tmp_path/'project',(1920,1080))
    assert assets[0].width <= 1920 and (tmp_path/'project/materials/processed').exists()

def test_ignores_bad_extension(tmp_path):
    source=tmp_path/'in'; source.mkdir(); (source/'bad.txt').write_text('x')
    try: scan_and_process(source,tmp_path/'project')
    except ValueError as exc: assert 'no valid' in str(exc)
