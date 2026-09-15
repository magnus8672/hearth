"""Run the connector's bounded loopback TLS tests on the reference Linux guest."""
import os
import subprocess

from appliance import ssh_args
from dev import ROOT, go_executable


def main():
    binary = ROOT / '.hearth/bin/linux-amd64/hearth-connector-tests'
    binary.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([go_executable(), 'test', '-c', '-o', str(binary), './cmd/hearth-connector'],
                   cwd=ROOT / 'worker', env=os.environ | {'GOOS': 'linux', 'GOARCH': 'amd64', 'CGO_ENABLED': '0'}, check=True)
    with binary.open('rb') as stream:
        subprocess.run([str(item) for item in ssh_args()] + ['umask 077; mkdir -p /opt/hearth/.hearth/bin; cat > /opt/hearth/.hearth/bin/hearth-connector-tests; chmod 700 /opt/hearth/.hearth/bin/hearth-connector-tests'], stdin=stream, check=True)
    subprocess.run([str(item) for item in ssh_args()] + ['/opt/hearth/.hearth/bin/hearth-connector-tests -test.v'], check=True)


if __name__ == '__main__':
    main()
