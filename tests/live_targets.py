"""Explicit operator configuration for opt-in live inference checks."""
import os
from urllib.parse import urlsplit


def configured_provider(prefix='HEARTH_TEST_PROVIDER'):
    url = os.environ.get(prefix + '_URL', '').rstrip('/')
    model = os.environ.get(prefix + '_MODEL', '').strip()
    if not url or not model:
        raise ValueError(f'Set {prefix}_URL and {prefix}_MODEL privately before live inference tests.')
    parsed = urlsplit(url)
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment
            or parsed.hostname.endswith(('.invalid', '.example'))):
        raise ValueError('A live provider requires an explicit HTTP(S) endpoint without URL credentials.')
    return url, model
