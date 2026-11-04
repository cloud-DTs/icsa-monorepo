#!/bin/bash
set -e
for twin in Battery PV; do
    cp -r ./DigitalTwinProfileSysMLv2/output/$twin/. ./digital-twin-manager/
    cp config_credentials.json ./digital-twin-manager/
    cd digital-twin-manager/src
    echo "destroy" | python main.py || true
    cd ../..
done


cd CloudDeployerTestSimulator
pulumi destroy --yes
cd ..

cd output
terraform destroy -auto-approve
