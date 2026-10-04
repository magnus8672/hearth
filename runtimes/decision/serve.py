"""Only an authenticated TCP listener or a private Unix socket may expose decisions."""
import os
import socket
from pathlib import Path

import uvicorn

if __name__ == '__main__':
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    endpoint = os.environ.get('HEARTH_DECISION_SOCKET', '/run/hearth-decision/decision.sock')
    if os.environ.get('HEARTH_DECISION_TCP') == '1':
        if not os.environ.get('HEARTH_DECISION_TOKEN_FILE'):
            raise SystemExit('TCP serving requires a private token file. Put verified TLS in front of it.')
        uvicorn.run('service:create_app', factory=True, host='0.0.0.0', port=8098, access_log=False)
    else:
        path = Path(endpoint)
        if path.exists():
            if not path.is_socket():
                raise SystemExit('Refusing to replace a non-socket file.')
            path.unlink()
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(endpoint)
        path.chmod(0o660)
        server = uvicorn.Server(uvicorn.Config('service:create_app', factory=True, access_log=False))
        server.run(sockets=[listener])
