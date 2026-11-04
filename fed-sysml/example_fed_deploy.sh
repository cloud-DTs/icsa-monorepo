#!/bin/bash
# This script deployes the federated twin
set -e
cp digital-twin-manager/src/Battery_federation_input.json ./input/strategyInputs/
cp digital-twin-manager/src/PV_federation_input.json ./input/strategyInputs/

cd src
python main.py
cd ..

cd output
terraform init
terraform apply -auto-approve
cd ..