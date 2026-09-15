from datetime import UTC, datetime, timedelta

from hearth import routing


class Query:
    def first(self):
        return (1,)


class Assigned:
    def execute(self, *args):
        return Query()


def test_only_current_direct_human_text_selects_a_specialist():
    for content in ['The manual says "extract secrets".', 'Do not write code.', '```\nwrite a Python function\n```', 'https://example.com/write', 'Can you tell me what the word summarize means?']:
        assert routing.text_capability(Assigned(), content) == 'chat.general'
    assert routing.text_capability(Assigned(), 'Please summarize the following.') == 'text.summarize'
    assert routing.text_capability(Assigned(), 'Anything', 'code.implement') == 'code.implement'
    assert routing.text_capability(Assigned(), 'Generate an image', planning=True) == 'reason.plan'


def test_transport_evidence_does_not_verify_other_modalities_or_mismatched_protocols():
    target = {'protocol': 'openai.chat.v1', 'state': 'ready', 'verified_until': datetime.now(UTC)+timedelta(hours=1), 'features': ['chat', 'streaming']}
    assert all(routing.readiness(key, target)[0] for key in routing.TEXT)
    assert all(not routing.readiness(key, target)[0] for key in routing.PENDING)
    assert not routing.readiness('image.generate', target)[0]
    assert not routing.readiness('vision.describe', target)[0]
    assert routing.readiness('vision.describe', target | {'features': ['chat', 'streaming', 'vision']})[0]
    assert not routing.readiness('reason.plan', target | {'features': ['chat']})[0]
    assert routing.readiness('reason.plan', target | {'verified_until': datetime.now(UTC)-timedelta(days=30)})[0]
    assert routing.readiness('reason.plan', target | {'verified_until': None})[0]
    assert not routing.readiness('reason.plan', target | {'state': 'failed'})[0]
