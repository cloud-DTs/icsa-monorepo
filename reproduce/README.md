# Reproduce the case studies

This folder deploys the two SysML v2 models of the case studies and measures the
resulting twins. The models are the input: the roles of TWINFRA are annotations
in the model, and everything else is derived from them.

| Case study | Twin | Model | What the model describes |
| --- | --- | --- | --- |
| CS1: charging point station | `MGridICSA` | [`models/MGridICSA.sysml`](models/MGridICSA.sysml) | 8 entities (the micro grid, a battery, a PV system and 5 chargers) with 14 components and 5 conditions that trigger the strategy action `balance` |
| CS2: virtual power plant | `VPP` | [`models/VPPMicrogrid.sysml`](models/VPPMicrogrid.sysml) | 100 households, each with a `Sensor` and a `BESS` component, and one condition with the strategy action `mqttProbe`; see the [scale settings](docs/vpp-microgrid.md) |

A model annotates its elements with roles, for example (excerpt) in
[`MGridICSA.sysml`](models/MGridICSA.sysml):

```sysml
#Entity def Battery {
    #component sensor : PAC_Sensor {
        #measureAttribute power { :>> dataType default AttributeDataType::DOUBLE; }
    }
    #component controller : BatteryController;
}
```

Three tools turn a model into a measured twin. The SysML v2 **parser**
([`sysml-v2-adapter`](../sysml-v2-adapter/README.md)) reads the model and writes
the configuration files that the **deployer**
([`digital-twin-manager`](../digital-twin-manager/README.md)) needs. The
deployer provisions the resources on AWS, and the **evaluator**
([`digital-twin-evaluator`](../digital-twin-evaluator/README.md)) measures the
latency of the deployed twin. Every Compose service runs once and exits. No
licensed software is needed.

## Requirements

- Docker with Compose and Linux containers.
- AWS credentials and a region. The deployer creates and removes resources in
  your account, and the evaluator publishes MQTT messages to the deployed twin.
  Permissions are listed in the [AWS permissions](../digital-twin-manager/docs/aws-permissions.md).
  Deploying costs money: CS1 creates 213 resources and CS2 creates 1,968.

## Setup

```bash
cd reproduce
cp .env.example .env
```

Fill in the AWS values in `.env`. `TWIN` selects the case study for
the deployer and the evaluator. The file preselects CS1. Build the images:

```bash
docker compose build
```

## Run CS1

```bash
# 1. Convert the model for the deployer. These two steps write generated
#    files to work/ that need no attention.
docker compose run --rm parse /pipeline/output/MGridICSA /pipeline/input/MGridICSA.sysml

docker compose run --rm stage MGridICSA

# 2. Deploy. At the prompt, type: deploy   then: exit
docker compose run --rm deployer

# 3. Inspect the evaluation without any AWS call, then measure both paths
docker compose run --rm evaluate plan mqtt --deployment /evaluation/deployment --config /evaluation/configs/MGridICSA.mqtt.json
docker compose run --rm evaluate run mqtt --deployment /evaluation/deployment --config /evaluation/configs/MGridICSA.mqtt.json --output /evaluation/results
docker compose run --rm evaluate run mqtt-twinmaker --deployment /evaluation/deployment --config /evaluation/configs/MGridICSA.mqtt-twinmaker.json --output /evaluation/results

# 4. Remove the twin. At the prompt, type: destroy   then: exit
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
docker compose run --rm parse /pipeline/output/VPP /pipeline/input/VPPMicrogrid.sysml
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
