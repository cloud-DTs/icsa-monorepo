# Federated Twin Strategy Tool

This tool lets you combine ("federate") strategies from multiple deployed digital twins into a single new strategy. It generates one AWS Lambda pipeline per new strategy. The pipeline collects current input values, runs your custom strategy code, and publishes the result as feedback, either internally or to an external MQTT broker.

## Prerequisites

- Python 3.x
- Access to the `digital-twin-manager` (https://github.com/cloud-DTs/digital-twin-manager) and the twins you want to federate already deployed through it

## Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

### Docker

Build the image and generate `output/main.tf`:

```bash
docker compose build
docker compose run --rm fed-sysml
```

Terraform commands run inside the same image and use the mounted `output`
directory:

```bash
docker compose run --rm fed-sysml terraform init
docker compose run --rm fed-sysml terraform apply
```

AWS credentials are read from the corresponding host environment variables,
including `AWS_SESSION_TOKEN` when temporary credentials are used.

## How it works

The tool packages three internal phases into one Lambda deployment:

```
Event checker -> Pipeline Lambda: collect -> strategy -> feedback
```

- **Collector phase**: gathers the current values of every twin/strategy you reference in `fedtwin.json`.
- **Your combined strategy**: your `lambda_function.py`, which receives all collected values as input and computes a new result.
- **Feedback phase**: takes the return value of your strategy and publishes it over MQTT, either to the internal broker or to an external one, depending on `feedback.type`.

The generated SSM registry entry contains the pipeline Lambda ARN with `type = "lambda"`. The `digital-twin-manager` event checker invokes it asynchronously.

If you already have a deployment based on the previous three-Lambda Step Functions workflow, follow the [migration guide](MIGRATION.md) before applying the newly generated Terraform.

To set up the tool, you need to provide four things, described below.

## 1. Federation input file

For every twin you want to federate, you first need its `<TwinName>_federation_input` file. You get this from the `digital-twin-manager` after deploying that twin — it's exported automatically as part of the deployment process.

Place each of these files in:

```
./input/strategyInputs
```

This is what tells the tool which strategies and attributes actually exist on each twin, so it can validate and wire up the `fedtwin.json` config below.

## 2. `fedtwin.json` — defining the federation

This file describes which strategies from which twins get combined into a new one, and what happens to the result.

```json
{
  "fedTwins": [
    {
      "name": "MicroGrid",
      "newStrategies": [
        {
          "name": "ConsumptionStrategy",
          "pathToCode": "sysml/testLambdaFunctions/fedTwinCombinedStrategy",
          "feedback": {
            "type": "INTERNAL",
            "topic": "Battery/iot-data"
          },
          "strategies": ["PV.production", "Battery.status"]
        }
      ]
    }
  ]
}
```

Field by field:

- **`fedTwins[].name`** — the name of the (virtual) federated twin this new strategy belongs to, e.g. `MicroGrid`.
- **`newStrategies[].name`** — the name of the new, combined strategy you're creating, e.g. `ConsumptionStrategy`.
- **`pathToCode`** — path to the folder containing your combined `lambda_function.py` (see section 4). Relative paths are resolved from the directory containing `fedtwin.json`.
- **`feedback.type`** — `INTERNAL` or `EXTERNAL`:
  - `INTERNAL`: the result is published over MQTT to the aws internal broker.
  - `EXTERNAL`: the result is published over MQTT to an outside broker. In this case you also need a `"brokerKey": "<a key in brokerConfig.json>"` here, pointing at one of the broker entries described in section 3.
- **`feedback.topic`** — the MQTT topic the result gets published to, e.g. `Battery/iot-data`.
- **`strategies`** — the list of input strategies being combined, written as `Twin.strategyName`, e.g. `PV.production` and `Battery.status`. These are the strategy inputs the collector phase will fetch and pass into your strategy code.

## 3. `brokerConfig.json` — only needed for external feedback

If any of your strategies use `"type": "EXTERNAL"` feedback, you also need a `brokerConfig.json` defining the broker(s) to publish to:

```json
{
  "brokers": {
    "default": {
      "broker_url": "broker.hivemq.com",
      "broker_port": 1883,
      "broker_username": "",
      "broker_password": ""
    },
    "eu_broker": {
      "broker_url": "cc673a1ab883421dbfcd225d0e26e925.s1.eu.hivemq.cloud",
      "broker_port": 8883,
      "broker_username": "Test12345678",
      "broker_password": "Test12345678",
      "use_tls": true
    }
  }
}
```

Each top-level key (`default`, `eu_broker`, ...) is a broker profile you can reference by name via `brokerKey` in `fedtwin.json`. `use_tls` is optional and only needed for brokers that require TLS (like the HiveMQ Cloud example above, which uses port `8883`).

## 4. `lambda_function.py` — your combined strategy logic

Your combined strategy must be a Python file named exactly `lambda_function.py`, with a `lambda_handler(event, context)` entry point — standard AWS Lambda signature.

```python
import json
from time import time
from datetime import datetime, timezone

def lambda_handler(event, context):
    kombi_data = event.get("ConsumptionStrategy", {})
    pv_data = kombi_data.get("production", {})
    battery_data = kombi_data.get("status", {})

    pv_power = pv_data.get("generatedPower", 0.0)
    charge_value = battery_data.get("chargeValue", 0.0)

    base_battery_consumption = float(charge_value) * 1.0
    effective_consumption = base_battery_consumption - float(pv_power)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "iotDeviceId": "SwiB9jTPm8kzDXz6chmo5T",
            "time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "consumption": effective_consumption,
        })
    }
```

### Accessing input values

The collector phase puts every input strategy's current values into `event`, keyed by your **new strategy's name** (not the source twin's name). From there, drill down by strategy name and attribute:

```
event["YourStrategyName"]["theSingleStrategyName"]["theAttribute"]
```

In the example above, the new strategy is called `ConsumptionStrategy`, so:

- `event["ConsumptionStrategy"]["production"]["generatedPower"]` — comes from `PV.production`
- `event["ConsumptionStrategy"]["status"]["chargeValue"]` — comes from `Battery.status`

Note that only the strategy name (`production`, `status`) is used as the key inside `event["ConsumptionStrategy"]`, not the twin name (`PV`, `Battery`) — the twin name in `fedtwin.json`'s `strategies` list is only there to tell the collector phase _where_ to fetch the value from.

### Return value and feedback behavior

Whatever your `lambda_handler` returns is passed to the feedback phase, which handles it in one of two ways:

1. **If your return value has a `body` field** (as in the example above), the feedback phase takes the contents of `body` _only_ — without the surrounding `statusCode`/`body` wrapper — and publishes that to the configured topic.
2. **Otherwise**, it publishes the entire return value as-is.

So in the example, what actually gets published to `Battery/iot-data` is just:

```json
{
  "iotDeviceId": "SwiB9jTPm8kzDXz6chmo5T",
  "time": "2026-06-21T10:15:30.123Z",
  "consumption": 12.5
}
```

not the outer `{"statusCode": 200, "body": "..."}` object.
