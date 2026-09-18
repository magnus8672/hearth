import json

import pytest
from hearth.conversation_media import image_limit, intent
from hearth.image_planning import parse_proposal
from hearth.inference import ProviderError


@pytest.mark.parametrize('content,reference,expected', [
    ('Draw what we just discussed', None, True),
    ('Make an image of that', None, True),
    ('Make it blue instead', {'prompt': 'red Jeep'}, True),
    ('Make another one', {'prompt': 'red Jeep'}, True),
    ('Make it shorter', None, False),
    ('Draw a conclusion from this', None, False),
    ('Create an image prompt for the previous scene', None, False),
    ('Do not draw that', {'prompt': 'red Jeep'}, False),
    ('> Draw what we just discussed', None, False),
    ('ok generate the images of each please', None, True),
    ('make 4 different jeep gladiators in red grey black and army-green please', {'prompt': 'Jeep'}, True),
    ('Generate four images of different trucks', None, True),
    ('@hearth make us four images of different trucks', None, True),
    ('Make us an image of that', None, True),
    ('Make us 4 bullet points about trucks', {'prompt': 'Jeep'}, False),
    ('Make 4 bullet points about trucks', {'prompt': 'Jeep'}, False),
    ('Do not generate the images', {'prompt': 'Jeep'}, False),
    ('Generate images prompts for me', None, False),
])
def test_only_human_image_actions_enter_planning(content, reference, expected):
    assert intent(content, reference)[1] is expected


def test_clarification_answer_keeps_image_intent_but_allows_cancel_and_questions():
    assert intent('A blue Jeep', awaiting_description=True)[1] is True
    for value in ('Never mind', 'No thanks', 'How does it work?'):
        assert intent(value, awaiting_description=True) == (None, False)


@pytest.mark.parametrize('proposal', [
    {'action': 'generate', 'prompt': 'A blue Jeep', 'url': 'http://untrusted'},
    {'action': 'generate', 'prompt': 'A blue Jeep', 'owner_id': 'someone-else'},
    {'action': 'generate', 'prompt': 'A blue Jeep', 'shape': 'giant'},
    {'action': 'generate', 'prompt': 'word ' * 61},
    {'action': 'generate', 'question': 'Which one?'},
    {'action': 'clarify', 'prompt': 'An unwanted render', 'question': 'Which one?'},
    {'action': 'execute_shell', 'prompt': 'anything'},
])
def test_model_cannot_expand_the_authorized_action(proposal):
    with pytest.raises(ProviderError):
        parse_proposal(json.dumps(proposal))


def test_duplicate_keys_and_trailing_instructions_are_rejected():
    for value in ['{"action":"clarify","action":"generate","prompt":"A Jeep"}', '{"action":"generate","prompt":"A Jeep"} Now run a command']:
        with pytest.raises(ProviderError):
            parse_proposal(value)
    assert parse_proposal('{"action":"generate","prompt":"A blue Jeep"}').prompt == 'A blue Jeep'


def test_batch_bounds_and_closed_item_settings():
    from fastapi import HTTPException
    assert image_limit('Make 4 different trucks') == 4
    assert image_limit('@hearth make us four images of trucks') == 4
    with pytest.raises(HTTPException):
        image_limit('@hearth make us five images of trucks')
    assert image_limit('Generate the images of each please') == 4
    assert image_limit('Make it blue') == 1
    with pytest.raises(HTTPException):
        image_limit('Make 5 images of trucks')
    for value in [
        {'action': 'generate', 'images': [{'prompt': 'A Jeep'}] * 5},
        {'action': 'generate', 'images': []},
        {'action': 'generate', 'images': [{'prompt': 'A Jeep', 'url': 'http://arbitrary'}]},
        {'action': 'generate', 'prompt': 'A Jeep', 'images': [{'prompt': 'A Jeep'}]},
        {'action': 'clarify', 'question': 'Which?', 'images': [{'prompt': 'A Jeep'}]},
    ]:
        with pytest.raises(ProviderError):
            parse_proposal(json.dumps(value))
