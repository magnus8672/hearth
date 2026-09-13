#!/bin/sh
set -eu
# Reference development PKI only. Production needs offline root custody and restricted issuance templates.
if [ ! -f /home/step/config/ca.json ]; then
    step ca init --name 'Hearth Development CA' --dns 'step-ca,localhost,127.0.0.1' \
        --address ':9000' --provisioner 'hearth-control' \
        --password-file /run/secrets/ca-password --provisioner-password-file /run/secrets/ca-password
fi
