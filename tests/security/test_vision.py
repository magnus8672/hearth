import base64
import io

import pytest
from fastapi import HTTPException
from hearth import vision
from hearth.config import Settings
from hearth.inference import ProviderError
from PIL import Image


def test_images_are_decoded_resized_and_stripped_of_metadata():
    data = io.BytesIO()
    photo = Image.new('RGB', (3000, 1800), 'red')
    exif = Image.Exif()
    exif[270] = 'Private metadata canary'
    photo.save(data, 'JPEG', exif=exif)
    raw, width, height = vision.normalize_image(data.getvalue())
    assert (width, height) == (1600, 960)
    with Image.open(io.BytesIO(raw)) as result:
        assert result.format == 'JPEG' and not result.getexif()
    assert b'Private metadata canary' not in raw


@pytest.mark.parametrize('raw', [b'<svg onload="alert(1)"></svg>', b'not an image', b'\x89PNG\r\n\x1a\n', b'x' * (8_388_608 + 1)], ids=['svg', 'non-image', 'truncated', 'oversized'])
def test_non_images_truncation_and_oversized_uploads_are_rejected(raw):
    with pytest.raises(HTTPException):
        vision.normalize_image(raw)


def test_animated_images_are_rejected():
    output = io.BytesIO()
    Image.new('RGB', (16, 16), 'red').save(output, 'WEBP', save_all=True, append_images=[Image.new('RGB', (16, 16), 'blue')], duration=100)
    with pytest.raises(HTTPException):
        vision.normalize_image(output.getvalue())


def test_context_image_budget_and_explicit_text_omit_pixels():
    messages = [{'role': 'user', 'content': 'Look here', 'attachment_ids': ['fixture'] * 5}]
    with pytest.raises(HTTPException, match='four image references'):
        vision.with_images(None, 'fixture-chat', messages, enabled=True)
    context = vision.with_images(None, 'fixture-chat', messages, enabled=False)
    assert isinstance(context[0]['content'], str)
    assert 'pixels are not included' in context[0]['content']


def test_vision_verification_requires_pixels_and_exact_challenge_answer(monkeypatch):
    monkeypatch.setattr(vision.secrets, 'randbelow', lambda n: 7)
    captured = []

    def stream(*args, **kwargs):
        content = args[3][0]['content']
        captured.append(content)
        assert '777777' not in content[0]['text']
        raw = base64.b64decode(content[1]['image_url']['url'].split(',')[1])
        with Image.open(io.BytesIO(raw)) as picture:
            assert picture.size == (640, 180)
        yield 'text', '777777'
        yield 'done', 'stop'

    monkeypatch.setattr(vision, 'chat_stream', stream)
    assert vision.probe('unused', '', 'fixture', Settings(mode='test'))['vision_probe'] == 'pixel-digits.v1'
    assert captured
    monkeypatch.setattr(vision, 'chat_stream', lambda *a, **kw: iter([('text', 'I cannot see images'), ('done', 'stop')]))
    with pytest.raises(ProviderError, match='image-reading'):
        vision.probe('unused', '', 'fixture', Settings(mode='test'))
