# Reproduce the case studies

This folder runs the three tools of TWINFRA in order: the SysML v2 **parser**
([`sysml-v2-adapter`](../sysml-v2-adapter/README.md)) turns a model into the
deployer's configuration files, the **deployer**
([`digital-twin-manager`](../digital-twin-manager/README.md)) provisions the
resources on AWS, and the **evaluator**
([`digital-twin-evaluator`](../digital-twin-evaluator/README.md)) measures the
latency of the deployed twin. Every Compose service runs once and exits. No
licensed software is needed.

| Case study | Twin | Model |
| --- | --- | --- |
| CS1: charging point station | `MGridICSA` | [`models/MGridICSA.sysml`](models/MGridICSA.sysml) |
| CS2: virtual power plant, 100 households | `VPP` | [`models/VPPMicrogrid.sysml`](models/VPPMicrogrid.sysml), see [scale settings](docs/vpp-microgrid.md) |

## Requirements

- Docker with Compose and Linux containers.
- A GitHub token with `read:packages` access. Maven uses it to download the SysML
  v2 library while building the parser image.
- AWS credentials and a region. The deployer creates and removes resources in
  your account, and the evaluator publishes MQTT messages to the deployed twin.
  Permissions are listed in the [AWS permissions](../digital-twin-manager/docs/aws-permissions.md).
  Deploying costs money: CS1 creates 213 resources and CS2 creates 1,968.

## Setup

```bash
cd reproduce
cp .env.example .env
```

Fill in `GH_TOKEN` and the AWS values in `.env`. `TWIN` selects the case study for
the deployer and the evaluator. The file preselects CS1. Build the images:

```bash
docker compose build
```

## Run CS1

```bash
# 1. Parse the model into configuration files (work/parse/)
docker compose run --rm parse /pipeline/output /pipeline/input/MGridICSA.sysml

# 2. Copy the twin's configuration to the deployer's input (work/MGridICSA/input/)
docker compose run --rm stage MGridICSA

# 3. Deploy. At the prompt, type: deploy   then: exit
docker compose run --rm deployer

# 4. Inspect the evaluation without any AWS call, then measure both paths
docker compose run --rm evaluate plan mqtt --deployment /evaluation/deployment --config /evaluation/configs/MGridICSA.mqtt.json
docker compose run --rm evaluate run mqtt --deployment /evaluation/deployment --config /evaluation/configs/MGridICSA.mqtt.json --output /evaluation/results
docker compose run --rm evaluate run mqtt-twinmaker --deployment /evaluation/deployment --config /evaluation/configs/MGridICSA.mqtt-twinmaker.json --output /evaluation/results

# 5. Remove the twin. At the prompt, type: destroy   then: exit
docker compose run --rm deployer
```

`mqtt` is the reaction path (client MQTT, processing and event action, client
MQTT). `mqtt-twinmaker` is the visualization path (client MQTT until the value is
readable through TwinMaker). Results are written to
`work/results/<twin>/<run-id>/` as `measurements.csv` and `summary.json`, the
format of [`evaluator-artifacts`](../evaluator-artifacts/).

## Run CS2

In `.env`, set `TWIN=VPP` and `DEPLOY_MANAGED_GRAFANA=false`. Then repeat the
five steps with `VPPMicrogrid.sysml`, `VPP` and the configurations
`VPP.mqtt.json` and `VPP.mqtt-twinmaker.json`:

```bash
docker compose run --rm parse /pipeline/output /pipeline/input/VPPMicrogrid.sysml
docker compose run --rm stage VPP
```

The deployed twin of CS2 contains the `mqttProbe` mock action
([`code/vpp/mqtt-probe`](code/vpp/mqtt-probe/lambda_function.py)). CS1 uses the mock
[`energy-management`](code/microgrid/energy-management/lambda_function.py) action.
Both return their input values to exercise the infrastructure. They do not
evaluate control algorithms.

## What to check

- **Resources.** After a deployment, count what exists in AWS and compare it with
  the allocation formula:
  `uv run python digital-twin-manager/scripts/resource_inventory.py --twin MGridICSA`
  (needs `uv` and AWS credentials with read access). The paper's numbers are 213
  for CS1 and 1,968 for CS2.
- **Latency.** `evaluator-artifacts/scripts/e2e_pgf.py` turns the
  `measurements.csv` files into the box plots of the paper.
- **Security.** `digital-twin-manager/docs/security-audit.md` runs the audit of the
  paper, and `evaluator-artifacts/scripts/security_pgf.py` draws its results.

## About the evaluator

- It reads the deployer's saved state in `work/<twin>/output/.digital-twin-manager-state/`.
  A twin is evaluated only after a completed `deploy`. Otherwise the evaluator
  fails instead of guessing.
- Planning (`plan`) is offline. `run` publishes a fresh random value per cycle,
  with 10 warmup and 100 measured cycles by default, and one writer.
- Its credentials need `iot:Connect`, `iot:Publish`, `iot:Subscribe`,
  `iot:Receive` and `iot:DescribeEndpoint`. The visualization path also needs the
  TwinMaker read permissions `GetPropertyValueHistory`, `GetWorkspace`,
  `GetEntity` and `GetComponentType`.
- The evaluator never creates or changes AWS resources.

## Without Docker

Each tool runs on its own:

- **Parser:** Java 21 and Maven, with the token in the Maven settings for the
  server id `cloud-dts`:
  `python sysml-v2-adapter/main.py models/MGridICSA.sysml -o work/parse`.
- **Deployer:** Python 3.13 and `uv`. Copy the four configuration files and
  `config_providers.json.example` (as `config_providers.json`) into one folder,
  then run `uv sync --locked` and `uv run python src/main.py` in
  `digital-twin-manager`, with `DIGITAL_TWIN_MANAGER_CONFIG_DIR` pointing at that
  folder. The models give the action code as `/pipeline/code/...`, and the
  deployer reads that path literally, so `/pipeline/code` must point to
  `reproduce/code` (for example through a symbolic link).
- **Evaluator:** `pip install ./digital-twin-evaluator` and
  `python -m digital_twin_evaluation run mqtt --deployment <output folder> --config <json>`.

## Contents

| Path | Purpose |
| --- | --- |
| `docker-compose.yaml`, `.env.example` | The four services and their settings |
| `stage.py` | Copies one twin's configuration from the parser output to the deployer input |
| `models/` | The SysML v2 models of both case studies and the VPP template |
| `code/` | The mock actions that the models reference |
| `evaluation/` | Evaluator settings per twin |
| `scripts/generate_vpp_microgrid.py` | Generates the VPP model for any number of households |
| `tests/` | Tests of the generator and the mock action |
| `work/` | Generated state and results (ignored by Git) |
