#Prerequisits

Install Pulumi, Terraform

Create a config_credentials.json
```bash
{
  "aws_access_key_id": "XXXXXXXXXXXXXXXXXXXX",
  "aws_secret_access_key": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "aws_region": "eu-central-1"
}

```bash
python -m venv .venv
```
```bash
cd DigitalTwinProfileSysMLv2
pip install -r requirements.txt 
cd ..
```
Starting the docker(when not started)
```bash
cd DigitalTwinProfileSysMLv2
cd apiserver
docker-compose up -d
cd ..
cd ..
```
Enter your absolute path of ./testLambdaFunctions/battery/status and ./testLambdaFunctions/py/production in ./input/sysml/Battery.sysml stats strategy and ./input/sysml/PV.sysml production strategy

```bash
cd DigitalTwinProfileSysMLv2
python -m src.main ../input/sysml
cd ..
```

cp config_credentials.json ./digital-twin-manager

For each of the content in ./DigitalTwinProfileSysMLv2/output/Battery and ./DigitalTwinProfileSysMLv2/output/PV
1. paste the conntent in ./digital-twin-manager
2. cd ./digital-twin-manager
3. python main.py
4. its a interactive program. Execute deploy


Then start the simulator
```bash
cp -r ./DigitalTwinProfileSysMLv2/output/Battery/. ./CloudDeployerTestSimulator/input/
cp -r .config_credentials.json ./CloudDeployerTestSimulator/input/
cd CloudDeployerTestSimulator
pip install -r requirements.txt
pulumi login --local
pulumi package add terraform-provider hashicorp/local
export PULUMI_CONFIG_PASSPHRASE=""
pulumi stack init dev


pulumi up
cd ..
```
Pulumi outputs the url of the simulator which is a web app


Copy federation input
```bash
cp digital-twin-manager/src/Battery_federation_input.json ./input/strategyInputs/
cp digital-twin-manager/src/PV_federation_input.json ./input/strategyInputs/
```

```bash
cd src
python main.py
cd ..
cd output
terraform init # first time
terraform apply
```
Federated Twin is now deployd

Destroying things
```bash
terraform destroy
pulumi destroy
in ./digitaltwin manager python main.py
```

I created also a bash script of this.
Before executing, dont forget to enter the your absolute path of ./testLambdaFunctions/battery/status and ./testLambdaFunctions/py/production in ./input/sysml/Battery.sysml stats strategy and ./input/sysml/PV.sysml production strategy and create a config_credentials.json a described above