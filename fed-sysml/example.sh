#!/bin/bash
# This script deployes the single twins PV and Battery
set -e

if [ ! -d ".venv" ]; then
    python -m venv .venv
fi
source .venv/bin/activate

cd DigitalTwinProfileSysMLv2
pip install -r requirements.txt 
pip install boto3
pip install shortuuid
cd ..

cd DigitalTwinProfileSysMLv2/apiserver
docker-compose up -d
cd ../..

cd DigitalTwinProfileSysMLv2
python -m src.main ../input/sysml
cd ..

for twin in Battery PV; do
    cp -r ./DigitalTwinProfileSysMLv2/output/$twin/. ./digital-twin-manager/
    cp config_credentials.json ./digital-twin-manager/
    
    cd digital-twin-manager/src
    echo "deploy" | python main.py || true

    cp ./${twin}_federation_input.json ../../input/strategyInputs/
    
    cd ../..
done

cp -r ./DigitalTwinProfileSysMLv2/output/Battery/. ./CloudDeployerTestSimulator/input/
cp config_credentials.json ./CloudDeployerTestSimulator/input/

cd CloudDeployerTestSimulator
pip install -r requirements.txt
pulumi login --local
pulumi package add terraform-provider hashicorp/local
export PULUMI_CONFIG_PASSPHRASE=""

pulumi stack init dev || true
pulumi up --yes  
cd ..
