# Digital Twin Manager

> **Note:** Ignore the run instructions in this README. Use the tool through the [`reproduce`](../reproduce/README.md) setup, which builds it and runs it together with the evaluator.

The deployer provisions the AWS resources of a digital twin (paper Section IV, contribution C2). It reads the configuration files that the parsers write and creates the resources that the roles of the twin require.

## How it works

1. **Configuration.** It reads and validates `config.json`, `config_hierarchy.json`, `config_iot_devices.json`, `config_events.json` and `config_providers.json`. The AWS credentials come from the environment. See [configuration files](docs/configuration-files.md).
2. **Provisioning.** It creates the resources in five groups (`core`, `iot`, `hierarchy`, `event_actions`, `init_values`) in an order that a dependency graph gives. See [role-based allocation](docs/role-based-allocation.md) and [core infrastructure layers](docs/core-infrastructure-layers.md).
3. **Runtime.** A device message passes the dispatcher and the processor of the device to the persister, which stores it. The Event Checker evaluates the conditions and starts the action and its feedback through the `lambda-chain` state machine. See [runtime ingestion flow](docs/runtime-ingestion-flow.md), [storage retention flow](docs/storage-retention-flow.md) and [events and actions](docs/events-and-actions.md).
4. **Names and security.** Every resource name starts with the twin name. The roles of the Lambda functions and services get policies scoped to the twin, and their trust policies are bound to the account. See [AWS resource naming](docs/aws-resource-naming.md) and [AWS permissions](docs/aws-permissions.md).

### Example

In [`MGridICSA.sysml`](../reproduce/models/MGridICSA.sysml), `MicroGrid.charger1.p13.power` is a measured value, and the condition `charger1Changed` compares it with a threshold. The [Event Checker](lambda_functions/core/event-checker/lambda_function.py) reads the latest values and supplies them to the action `balance1`. The feedback of the action targets `MicroGrid.battery.controller`. The [v2 parser](../sysml-v2-adapter/exporter/src/main/java/org/example/TwinExporter.java) turns these references into the configuration, and the deployer supplies the ingestion and feedback resources around the [action code](../reproduce/code/microgrid/energy-management/lambda_function.py).

## Commands

| Command | Effect |
| --- | --- |
| `deploy` | Creates all resources of the twin |
| `destroy` | Removes them |
| `info` | Lists the resources that exist |

The [`reproduce`](../reproduce/README.md) folder runs the deployer in Docker.

## Ingestion timing

With `DEBUG=True` in `.env`, the IoT rule adds `iot_ingested_at_ms` to each message and the persister stores `db_write_started_at_ms` and `ingestion_to_write_ms` with each record. They measure the delay from the IoT rule to DynamoDB. The default is `False`.
