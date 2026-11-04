# Digital twin evaluation in the pipeline

The evaluation service is a separate sibling project:

```text
cloud-dtc/
  cloud-dtc-docker/
  digital-twin-evaluation/
```

## Source of deployment data

Evaluation reads the applied manager snapshot from:

```text
pipeline/digital-twin-manager/deployments/<Twin>/output/
  .digital-twin-manager-state/
    metadata.json
    configs/
      config.json
      config_hierarchy.json
      config_iot_devices.json
```

This state identifies the actual deployed twin, AWS region, entity IDs, device
bindings, and property types. Pending deployer input and SysML are not used as
proof of a deployment. Missing state requires a completed deploy or manager
`init-state`; evaluation fails instead of guessing.

Experiment settings are separate. The default path is:

```text
pipeline/digital-twin-evaluation/input/<Twin>.<evaluation-type>.json
```

The provided `MGridICSA.roundtrip.json` uses storage mode and measures all seven
telemetry devices. `parameters.targets` lists each device's logical component
path, property, and test value:

| Device | Target | Property | Value |
| --- | --- | --- | --- |
| Battery | `MicroGrid.battery.p16` | `totalCapacity` | `100` |
| PV | `MicroGrid.pv.pV1` | `output` | `12.5` |
| Charger 1 | `MicroGrid.charger1.p13` | `consumption` | `12.5` |
| Charger 2 | `MicroGrid.charger2.p14` | `consumption` | `12.5` |
| Charger 3 | `MicroGrid.charger3.p12` | `consumption` | `12.5` |
| Charger 4 | `MicroGrid.charger4.p17` | `consumption` | `12.5` |
| Charger 5 | `MicroGrid.charger5.p11` | `consumption` | `12.5` |

The config sets `concurrency` to 20, allowing up to 20 roundtrip cycles across
all devices at once. Each device has 10 warmup cycles and 100 measured cycles:
70 warmup cycles and 700 measured cycles in total. All warmup cycles finish
before measured cycles begin. Set `concurrency` to 1 for sequential execution.
The worker queue is bounded, and timestamps remain unique per device.
All targets are
validated against applied state before any AWS call. These properties do not
match the deployed `power` conditions. The controller has no telemetry
properties, and generated constant components are excluded.

The single-target `target` / `property` / `value` format remains supported.

## CheckWatt roundtrip

The provided `CheckWatt.roundtrip.json` covers the saved 100-household CheckWatt
deployment. It selects all 201 telemetry devices: Grid telemetry and the Sensor
and BESS of `Household0001` through `Household0100`. CW has no telemetry device.

| Devices | Property | Value |
| --- | --- | --- |
| `Grid.telemetry` | `activePowerKW` | `12.5` |
| Each household's `Sensor` | `chargedEnergyKWh` | `100` |
| Each household's `BESS` | `stateOfChargePercent` | `50` |

The config uses storage mode, `samples: 5`, `warmup: 0`, and `concurrency: 10`.
This produces 201 * 5 = 1005 measured messages and no additional warmup messages.
At most 10 complete write/read cycles run at once. Sample counts apply per
device. For a different household count, update the targets and sample count to
keep the total near 1000.

Use these commands in the running orchestrator:

```text
plan evaluation roundtrip CheckWatt
evaluate roundtrip CheckWatt
```

The first command validates the config against the saved applied state without
AWS calls. The second command sends the measurement traffic.

## CheckWatt MQTT

`CheckWatt.mqtt.json` measures `Household0001.BESS.activePowerKW` through the
`mqttProbe` strategy and MQTT feedback:

```text
client -> MQTT -> dispatcher -> processor -> persister -> event-checker
       -> Step Functions -> mqttProbe -> event-feedback -> MQTT -> client
```

Convert the updated CheckWatt model and apply its manager plan before running
this evaluation. The action must exist in the applied `config_events.json`.
See [the CheckWatt model guide](checkwatt-microgrid.md#run-the-converter).

```text
plan evaluation mqtt CheckWatt
evaluate mqtt CheckWatt
```

The mock echoes the exact sent DOUBLE in `value`. The evaluator also checks
`action: mqttProbe`. The config uses values in `[1, 2)`, 100
measured samples, 10 warmups, a 10-second deadline, and `concurrency: 1`. Keep
one writer for the selected property during measurement. This measures one
component's complete feedback route; the storage evaluation above covers all
201 devices in the saved 100-household deployment.

## Commands

### MQTT to TwinMaker availability

The `mqtt-twinmaker` evaluation sends a fresh unique DOUBLE over MQTT, then polls
the native TwinMaker `GetPropertyValueHistory` API. Its timer stops when both the
sent timestamp and value appear in the API response:

```text
client -> MQTT -> dispatcher -> processor -> persister -> DynamoDB
client -> TwinMaker GetPropertyValueHistory -> hot-reader -> DynamoDB
```

The timer uses one client monotonic clock. UTC timestamps identify the stored
record; no Lambda/client clock subtraction is used. Connection setup is excluded.
This measures the first observed availability through TwinMaker, including query
duration and polling waits. Grafana datasource queries, panel refresh and browser
rendering are outside this measurement.

The provided configs select `Household0001.BESS.activePowerKW` for CheckWatt and
`MicroGrid.charger1.p13.power` for MGridICSA. Both use 100 measured samples, 10
warmups, a 10-second cycle deadline, a 0.1-second polling interval, and concurrency
1. Use one writer for the selected property. An in-flight SDK read may overrun
the deadline; a late matching response remains a timeout.

Build the updated evaluation image from the pipeline repository:

```powershell
docker build -t evbodanov/digital-twin-evaluation:latest ../digital-twin-evaluation
```

Then use the running pipeline terminal:

```text
plan evaluation mqtt-twinmaker CheckWatt
evaluate mqtt-twinmaker CheckWatt

plan evaluation mqtt-twinmaker MGridICSA
evaluate mqtt-twinmaker MGridICSA
```

Settings are in `pipeline/digital-twin-evaluation/input/<Twin>.mqtt-twinmaker.json`.
Planning is offline and reads the applied snapshot. No MQTT feedback action or
new deployment is required when the existing TwinMaker history connector works.
Normal configured business actions can still run after the telemetry is stored.

Evaluation credentials need MQTT `iot:Connect`/`iot:Publish` and TwinMaker
`GetPropertyValueHistory`, `GetWorkspace`, `GetEntity`, `GetComponentType` access
for the selected workspace/resources. Automatic endpoint discovery also uses
`iot:DescribeEndpoint`. The new flow does not invoke the reader Lambda directly.

Reports use the existing `<Twin>/<run-id>` output directories. `roundtrip_ms`
ends at the first verified TwinMaker response, `read_ms` sums history reads,
`write_ms` measures the local asynchronous publish call, and `publish_ack_ms`
records an observed broker acknowledgement. PUBACK is not success. CSV rows
include `response_timestamp`, `response_value` and `read_attempts`. Percentiles
exclude warmups and failed samples.

### Roundtrip commands

From the running orchestrator, first inspect the plan:

```text
plan evaluation roundtrip MGridICSA
```

Planning validates the saved deployment and settings without AWS calls. Start the
evaluation explicitly:

```text
evaluate roundtrip MGridICSA
```

This sends telemetry through the existing deployed resources. Evaluation does not
deploy or modify Lambda functions, tables, schemas, or rule configuration.

To select different settings, supply a config path relative to the pipeline
repository or an absolute path. Quote paths containing spaces:

```text
evaluate roundtrip MGridICSA "configs/my experiment.json"
```

To measure the full ingestion path, set `parameters.mode` to `ingestion` in an
evaluation config. Storage uses synchronous persister and reader calls. Ingestion
uses IoT Data HTTPS Publish -> dispatcher -> processor -> persister -> DynamoDB,
followed by the same reader Lambda. Both modes retain configured business rules.

Credentials come from the pipeline environment (`AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, and optional `AWS_SESSION_TOKEN`). The region comes from
the applied state. Deployment snapshots and settings are mounted read-only.
The service does not mount the Docker socket or change the active manager input.

## Results and interpretation

```text
pipeline/digital-twin-evaluation/output/<Twin>/<run-id>/
  summary.json
  measurements.csv
```

Reports are ignored by Git. They include source fingerprints, effective settings,
runtime versions, warmup samples, failures, read attempts, and client durations.
The CLI's `/evaluation/results/<Twin>/<run-id>` path is inside the container.
The bind mount saves those same files under the host directory shown above.
The orchestrator prints the absolute host directory after every evaluation run,
including runs that return a nonzero exit code because measurements failed.
For multiple devices, `summary.targets` provides separate counts and percentiles
per device. CSV rows include `target`, `property`, and `device_id`. A failed
device remains in the report while the evaluator continues with the others.
For parallel runs, the summary includes `duration_ms`, `measured_duration_ms`,
and `successful_samples_per_second`. Per-message `roundtrip_ms` excludes time
waiting for a worker slot; measured-phase duration includes that wait.
The evaluator checks the exact sent timestamp and value. It does not count a
successful API submission or an older database record as a completed roundtrip.

The reader's deployed consistency behavior is preserved. The full roundtrip
includes polling waits; `read_ms` reports the sum of reader calls. Percentiles
exclude failures and warmup samples, while their counts and raw rows remain in
the report. Cold starts are not inferred from call order.

The service has its own CLI and tests. New evaluations implement the common
evaluation interface and register under a new type name. The pipeline command
passes that type through; adding a type does not require another command handler.
