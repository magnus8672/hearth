"""Private, one-shot Compose console. This module has no HTTP listener."""

import argparse
import json
import os
import sys
import time

import httpx
from configure_identity import admin_client, configure, create_owner, owner_created


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['configure', 'owner', 'status'])
    args = parser.parse_args()
    values = dict(os.environ)
    try:
        if args.action == 'configure':
            # Production Keycloak builds its optimized runtime on first boot.
            for attempt in range(90):
                try:
                    with admin_client(values):
                        break
                except httpx.HTTPError:
                    if attempt == 89:
                        raise
                    time.sleep(2)
            configure(values)
        elif args.action == 'owner':
            create_owner(json.loads(sys.stdin.read(16384)), values)
            print('Owner created. Sign in to enroll your second factor and save recovery codes.')
        else:
            print(json.dumps({'owner_created': owner_created(values)}))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        # Provider errors may contain credentials. Do not print exception bodies.
        print('Head setup could not complete. Check that PostgreSQL and identity are ready.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
