import pytest
from hearth import inference
from hearth.config import Settings
from hearth.inference import ProviderError, endpoint
from hearth.providers import ConnectProvider, transport_settings
from pydantic import ValidationError


def resolved(monkeypatch, *addresses):
    monkeypatch.setattr(inference.socket, 'getaddrinfo', lambda *args, **kwargs: [(2, 1, 6, '', (address, 1234)) for address in addresses])


@pytest.mark.parametrize('mode', ['test', 'production'])
def test_http_approval_is_bound_to_one_canonical_connection(monkeypatch, mode):
    resolved(monkeypatch, '10.20.30.40')
    base = Settings(mode='test').model_copy(update={'mode': mode})
    approved = transport_settings({'base_url': 'http://models.home:1234/', 'allow_insecure_http': True}, base)
    with pytest.raises(ProviderError, match='accept the risks'):
        endpoint('http://models.home:1234', base)
    address, authority, _ = endpoint('http://models.home:1234/v1', approved)
    assert str(address) == 'http://10.20.30.40:1234/v1' and authority == 'models.home:1234'
    for other in ['http://other.home:1234', 'http://models.home:1235']:
        with pytest.raises(ProviderError, match='accept the risks'):
            endpoint(other, approved)
    assert not getattr(base, 'provider_http_approved_url', '')


@pytest.mark.parametrize('addresses', [
    ['169.254.169.254'], ['8.8.8.8'], ['100.100.100.200'], ['0.0.0.0'],
    ['::ffff:169.254.169.254'], ['192.168.1.4', '8.8.8.8'],
])
def test_approval_does_not_bypass_address_eligibility(monkeypatch, addresses):
    resolved(monkeypatch, *addresses)
    approved = transport_settings({'base_url': 'http://models.home:1234', 'allow_insecure_http': True}, Settings(mode='test'))
    with pytest.raises(ProviderError, match='eligible'):
        endpoint('http://models.home:1234', approved)


def test_approval_does_not_open_hearth_itself_or_accept_truthy_strings():
    address = 'http://127.0.0.1:8445'
    approved = transport_settings({'base_url': address, 'allow_insecure_http': True}, Settings(mode='test'))
    with pytest.raises(ProviderError, match='hearth application'):
        endpoint(address, approved)
    body = {'name': 'Fixture', 'base_url': 'https://192.168.1.4', 'model_id': 'fixture', 'local_only': True}
    with pytest.raises(ValidationError):
        ConnectProvider(**body, allow_insecure_http=True)
    with pytest.raises(ValidationError):
        ConnectProvider(**(body | {'base_url': 'http://192.168.1.4'}), allow_insecure_http='yes')
