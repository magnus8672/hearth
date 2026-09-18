import pytest
from fastapi import HTTPException
from hearth.conversation_media import image_prompt, image_shape


@pytest.mark.parametrize('content', [
    'Make an image of a fox beside a fireplace',
    '@hearth make us an image of a fox beside a fireplace please',
    'Could you draw us a fox beside a fireplace',
    'Create an image for us of a fox beside a fireplace',
    'Could you please generate me a picture of a fox beside a fireplace',
    'Draw me a fox beside a fireplace',
    'I would like an image of a fox beside a fireplace',
    'Hey hearth, paint a fox beside a fireplace',
    'Create a realistic illustration showing a fox beside a fireplace',
])
def test_direct_creation_requests(content):
    assert image_prompt(content).endswith('a fox beside a fireplace')


def test_requested_medium_style_and_orientation_are_preserved():
    content = 'I would like you to create a landscape photorealistic photo of a fox'
    assert image_prompt(content) == 'photorealistic photo of a fox'
    assert image_shape(content) == 'landscape'
    assert image_prompt('Can I have a logo of a little fire') == 'logo of a little fire'
    assert image_prompt('Please could you paint me a fox') == 'painting of a fox'


@pytest.mark.parametrize('content', [
    'How does image generation work?', 'Do not make an image of a fox',
    'Explain the prompt "Make an image of a fox"', '```Make an image of a fox```',
    '> Draw a fox', 'I have an image to discuss', 'Draw a conclusion from these results',
    'Could you write code to generate an image?', 'What would happen if I asked you to draw a fox?',
    'Make us an image prompt for a fox', 'Do not make us an image of a fox',
    '> @hearth make us an image of a fox', 'Explain how to make us an image',
    'Create an image prompt for a fox', 'Make an image generator with Python',
    'Make an image of a fox, but do not actually generate it, just explain the process',
])
def test_discussion_quotes_negation_and_code_do_not_trigger_generation(content):
    assert image_prompt(content) is None


@pytest.mark.parametrize('content', ['Make an image?', 'Make an image of that', 'Make an image of ' + 'x' * 1001])
def test_missing_ambiguous_or_oversized_description_requires_clarification(content):
    with pytest.raises(HTTPException) as problem:
        image_prompt(content)
    assert problem.value.status_code == 422
