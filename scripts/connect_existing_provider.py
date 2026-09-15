"""Explicit local maintenance entry point for the development appliance.

Connects only the named server/model using the restricted application role.
It preserves identity accounts and personal content and creates no browser session.
Run inside the admin API container, whose private configuration supplies the farm.
"""
import argparse
import json
from pathlib import Path

from hearth.config import Settings
from hearth.database import make_engine, scoped_session, verify_application_role
from hearth.policy import ROLES, Principal
from hearth.providers import ConnectProvider, create_target, probe_target
from sqlalchemy import text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--protocol', choices=['openai.chat.v1', 'hearth.image.v1'], default='openai.chat.v1')
    parser.add_argument('--credential-file', type=Path)
    args = parser.parse_args()
    settings = Settings()
    if settings.mode != 'development' or settings.audience != 'admin' or not settings.farm_id:
        raise SystemExit('Run this explicit development maintenance command inside the configured admin API container.')
    engine = make_engine(settings.database_url.get_secret_value())
    verify_application_role(engine)
    try:
        with engine.connect() as db:
            owners = db.execute(text("SELECT u.id,u.authorization_version FROM users u JOIN role_grants g ON g.user_id=u.id AND g.farm_id=u.farm_id WHERE u.farm_id=:farm AND u.state='active' AND g.role='Owner'"), {'farm': settings.farm_id}).mappings().all()
        if len(owners) != 1:
            raise SystemExit('This maintenance helper requires exactly one existing active Owner. Use the authenticated Providers screen otherwise.')
        principal = Principal(owners[0]['id'], settings.farm_id, ROLES['Owner'], owners[0]['authorization_version'])
        key = args.credential_file.read_text(encoding='utf-8').strip() if args.credential_file else ''
        data = ConnectProvider(name=args.name, base_url=args.base_url, model_id=args.model, local_only=True, protocol=args.protocol, api_key=key)
        from hearth.inference import normalize_url
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            target = db.execute(text('SELECT t.id,t.revision FROM inference_targets t JOIN provider_connections c ON c.id=t.connection_id WHERE c.base_url=:url AND t.model_id=:model'), {'url': normalize_url(args.base_url), 'model': args.model}).mappings().one_or_none()
        if target is None:
            target = create_target(engine, settings, principal, data)
        result = probe_target(engine, settings, principal, target['id'], target['revision'])
        print(json.dumps(result, default=str))
        if result['state'] != 'ready':
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
