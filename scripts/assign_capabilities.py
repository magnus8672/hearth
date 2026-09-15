"""Explicit developer-farm defaults, preserving every previously edited route."""
import argparse
import json

from hearth.catalog import CAPABILITIES
from hearth.config import Settings
from hearth.database import make_engine, scoped_session, verify_application_role
from hearth.policy import ROLES, Principal
from hearth.routing import RouteTarget, SetRoute, assign_route
from sqlalchemy import text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--defaults-to-existing-services', action='store_true', required=True)
    parser.parse_args()
    settings = Settings()
    if settings.mode != 'development' or settings.audience != 'admin' or not settings.farm_id:
        raise SystemExit('Use the configured development admin API container.')
    engine = make_engine(settings.database_url.get_secret_value())
    verify_application_role(engine)
    try:
        with engine.connect() as db:
            owners = db.execute(text("SELECT u.id,u.authorization_version FROM users u JOIN role_grants g ON g.user_id=u.id AND g.farm_id=u.farm_id WHERE u.farm_id=:farm AND u.state='active' AND g.role='Owner'"), {'farm': settings.farm_id}).mappings().all()
        if len(owners) != 1:
            raise SystemExit('Use Administration unless this development farm has exactly one active Owner.')
        principal = Principal(owners[0]['id'], settings.farm_id, ROLES['Owner'], owners[0]['authorization_version'])
        with scoped_session(engine, principal.id, principal.farm_id) as db:
            targets = db.execute(text("SELECT id,protocol FROM inference_targets WHERE state='ready' ORDER BY id")).mappings().all()
            existing = set(db.execute(text('SELECT capability_id FROM capability_routes')).scalars().all())
        text_models = [item['id'] for item in targets if item['protocol'] == 'openai.chat.v1']
        image_models = [item['id'] for item in targets if item['protocol'] == 'hearth.image.v1']
        if len(text_models) != 1 or len(image_models) != 1:
            raise SystemExit('Defaults require exactly one verified text target and one image target. Use Administration to choose among other targets.')
        result = []
        for capability in CAPABILITIES:
            key = capability.capability_id
            if key in existing:
                result.append({'capability': key, 'preserved': True})
                continue
            target = image_models[0] if key in {'image.generate', 'geometry.generate'} else text_models[0]
            row = assign_route(engine, principal, key, SetRoute(revision=1, targets=[RouteTarget(target_id=target, priority=100)]))
            result.append({'capability': key, 'ready': row['targets'][0]['ready'], 'executable': row['profile']['executable']})
        print(json.dumps({'assignments': result}))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
