# Digital twin evaluation

A batch service for repeatable evaluations of deployed digital twins. Run it as
a Python CLI or a Docker job. The first evaluation type is `roundtrip`.

## MQTT processing roundtrip

The `mqtt` evaluation measures client MQTT -> existing processing -> client MQTT.
Both client directions use MQTT, not the IoT Data HTTPS Publish API. The client
uses AWS IoT Device SDK v2, MQTT over WSS, and SigV4 credentials. Connection setup
and a confirmed QoS 1 subscription finish before warmup or measurement starts.

No provisioner change is needed when an existing processing path publishes a
reply that contains an unchanged input value. The supplied MGridICSA example
sends `charger1.power` in the range 1.0 to 2.0. Its applied `balance1` condition
is triggered by positive power. The current Balance handler returns
`inputs.charger1Power` and `action: balance1`; event-feedback publishes that result
to the controller topic. This measures processing feedback from the current mock
Balance action. It does not prove physical actuation.

```powershell
python -m pip install -e ".[test]"
python -m digital_twin_evaluation plan mqtt --deployment ../reproduce/work/MGridICSA/output --config examples/MGridICSA.mqtt.json
python -m digital_twin_evaluation run mqtt --deployment ../reproduce/work/MGridICSA/output --config examples/MGridICSA.mqtt.json --output results
```

Planning is offline. `feedback_action` resolves the exact reply topic from
applied `configs/config_events.json`; the report includes that file's
fingerprint. The adapter checks that the selected action has MQTT action-result
feedback and that it consumes and is triggered by the selected property. For a
different existing processing chain, supply `response_topic` instead of
`feedback_action`. The reply topic must differ from the telemetry publish topic.

| Parameter | Meaning |
| --- | --- |
| `target`, `property` | Applied telemetry component and a DOUBLE property |
| `value_range` | Two finite numeric bounds that keep the control condition true |
| `feedback_action` | Action name from the applied event configuration |
| `response_topic` | Explicit existing reply topic, instead of feedback_action |
| `response_value_path` | List of object keys to the echoed value; JSON-string envelopes such as body are supported |
| `response_match` | Additional exact top-level fields, for example action: balance1 |
| `endpoint` | Optional IoT endpoint hostname; otherwise discovered at run startup |
| `samples`, `warmup` | Measured and excluded cycle counts; defaults 100 and 10 |
| `timeout_seconds` | Per-cycle reply deadline; default 10 |
| `setup_timeout_seconds` | Connect/SUBACK budget and individual endpoint lookup timeout; default 10 |
| `concurrency` | Must be 1 for this initial value-correlation implementation |

Every cycle sends a fresh random DOUBLE within the configured range. Values are
unique across both warmup and measured cycles in the run. The range must provide
at least 40 bits of floating-point resolution for reliable correlation across
runs. Use one writer for the selected device, keep the returned value unchanged,
and stop other traffic that can trigger the same action during comparisons.
Actions that read latest database state can otherwise use a different input.
Do not use rounded, transformed, constant, or boolean command values as the echo.

The response waiter exists before publish. The client captures a monotonic time
at entry to the MQTT callback and accepts it only when topic, response fields,
and the exact sent numeric value match before the deadline. Own-topic messages,
retained messages, old values, duplicates, and late replies cannot finish another
cycle. PUBACK alone is not success. A connection interruption fails the active
and remaining cycles; the client does not silently reconnect and republish them.

For MQTT reports, `roundtrip_ms` ends at matched callback receipt, `write_ms`
records the local asynchronous publish call, including calls that fail.
`read_ms` is zero because there are no reader requests.
`publish_ack_ms` is the separately observed broker
acknowledgement time and can be null when a processing reply arrives first.
Raw CSV includes the actual `response_value`. Message diagnostics count matching,
ignored, malformed, duplicate, and late replies. Existing percentile rules apply.

AWS credentials need `iot:Connect`, `iot:Publish`, `iot:Subscribe`, and
`iot:Receive` for the configured client/topics. Automatic endpoint discovery also
needs `iot:DescribeEndpoint`; set `endpoint` explicitly to avoid that lookup.
The client reads credentials from the SDK provider chain. It does not read device
private keys from deployment snapshots or create AWS resources.

MQTT processing evaluation requires an applied action with a working feedback
route. The [`reproduce`](../reproduce/README.md) folder supplies a VPP `mqttProbe` mock for that path.
The `mqtt-twinmaker` evaluation below reads through TwinMaker and does not need
an action or MQTT feedback topic.

From the `reproduce` folder, the `evaluate` service runs the type with its
example config:

```text
docker compose run --rm evaluate plan mqtt --deployment /evaluation/deployment --config /evaluation/configs/MGridICSA.mqtt.json
docker compose run --rm evaluate run mqtt --deployment /evaluation/deployment --config /evaluation/configs/MGridICSA.mqtt.json --output /evaluation/results
```

The MQTT connection and callback APIs follow the official
[SDK connection builder](https://aws.github.io/aws-iot-device-sdk-python-v2/awsiot/mqtt_connection_builder.html)
and [CRT MQTT futures/callback contract](https://awslabs.github.io/aws-crt-python/api/mqtt.html).

## MQTT to TwinMaker visibility

The `mqtt-twinmaker` evaluation measures this flow:

```text
client -> MQTT -> dispatcher -> processor -> persister -> DynamoDB
client -> TwinMaker GetPropertyValueHistory -> hot-reader connector -> DynamoDB
```

Each cycle sends a fresh unique DOUBLE with a unique UTC millisecond timestamp.
One client monotonic timer starts before MQTT publish and stops after a
TwinMaker response contains that exact timestamp and value. The history query
uses the applied workspace, entity and component bindings, a narrow time window
around the sent timestamp, and no interpolation. UTC offsets and fractional
timestamp formatting are normalized without discarding nanosecond differences.
Each history page is checked before requesting the next page. Pagination stops
at the first matching timestamp and value or when the cycle deadline is reached.
Empty history is polled again; SDK errors are recorded as `read_error` and do
not fall back to direct Lambda invocation.

The publish connection uses MQTT over WSS with SigV4 and QoS 1. It does not
subscribe to feedback. PUBACK is diagnostic; it does not complete a cycle.
Connection setup and AWS client initialization are outside sample timing.
An interrupted MQTT connection prevents subsequent publishes in the run.

```powershell
python -m digital_twin_evaluation plan mqtt-twinmaker --deployment ../reproduce/work/VPP/output --config examples/VPP.mqtt-twinmaker.json
python -m digital_twin_evaluation run mqtt-twinmaker --deployment ../reproduce/work/VPP/output --config examples/VPP.mqtt-twinmaker.json --output results
```

Examples are provided for `Household0001.BESS.activePowerKW` in VPP and
`MicroGrid.charger1.p13.power` in MGridICSA. The first version supports one target
and `concurrency: 1`. Use one writer for the selected property. Existing business
rules can still execute after ingestion; the measurement does not wait for them.
No new strategy or provisioner change is needed when the history connector works.

| Parameter | Meaning |
| --- | --- |
| `target`, `property` | Applied telemetry component and a DOUBLE property |
| `value_range` | Finite numeric bounds for unique generated values |
| `samples`, `warmup` | Measured and excluded cycle counts; defaults 100 and 10 |
| `timeout_seconds` | Whole-cycle deadline; default 10 |
| `poll_interval_seconds` | Wait between unmatched reads; default 0.1 |
| `request_timeout_seconds` | SDK read timeout with no automatic retries; default 10 |
| `setup_timeout_seconds` | MQTT setup timeout; default 10 |
| `endpoint` | Optional existing IoT endpoint hostname |
| `concurrency` | Must be 1 |

An in-flight SDK history read can finish after the whole-cycle deadline. A
matching response after that deadline is a timeout. `roundtrip_ms` includes
polling waits and API response latency; `read_ms` is the sum of history reads,
`write_ms` is the local asynchronous publish call, and `publish_ack_ms` is the
observed broker acknowledgement time. CSV records preserve the received timestamp
and value. `read_attempts` counts polling attempts; one attempt can request
multiple history pages. Warmup and failed samples do not enter latency percentiles.

This measures the first observed availability through the TwinMaker API. Polling
interval and query duration affect that observation. Grafana datasource requests,
dashboard refresh and browser rendering are outside this metric. Both timer
endpoints are on the client; client/server clock subtraction is not used.

The client needs `iot:Connect`, `iot:Publish`, and, for automatic discovery,
`iot:DescribeEndpoint`. TwinMaker reads need `iottwinmaker:GetPropertyValueHistory`
and its `GetWorkspace`, `GetEntity`, and `GetComponentType` permissions scoped to
the selected workspace and resources. The connector retains its own execution
role. No direct `lambda:InvokeFunction` or MQTT Subscribe/Receive permission is
required by this evaluation.

The reader follows the official
[GetPropertyValueHistory API](https://docs.aws.amazon.com/iot-twinmaker/latest/apireference/API_GetPropertyValueHistory.html).

## Input

The primary input is the digital-twin-manager **applied state**. Pass a saved
deployment directory, its output directory, or `.digital-twin-manager-state`
directly. The adapter supports state version 1 and its AWS resource naming
contract. It reads the applied metadata and the three deployment configuration
files needed to resolve entities, components, device IDs, and property types.

The adapter never falls back to pending staging input. SysML is not an execution
input: it does not contain the final device IDs or prove what was deployed.
Credentials use the AWS SDK credential chain; credential files in the deployment
are not read. Evaluation settings are separate from deployment settings.

## Local use

Requires Python 3.12 or later.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m digital_twin_evaluation list
.\.venv\Scripts\python.exe -m digital_twin_evaluation plan roundtrip --deployment ../reproduce/work/MGridICSA/output --config examples/MGridICSA.roundtrip.json
```

`plan` validates input and resolves the experiment without creating AWS clients.
`run` sends measurement telemetry to the selected deployed device:

```powershell
.\.venv\Scripts\python.exe -m digital_twin_evaluation run roundtrip --deployment ../reproduce/work/MGridICSA/output --config examples/MGridICSA.roundtrip.json --output results
```

The installed entry point is `digital-twin-evaluation` with the same arguments.

## Docker

```powershell
docker build -t digital-twin-evaluation:local .
docker run --rm digital-twin-evaluation:local list
```

The [`reproduce`](../reproduce/README.md) folder provides the Compose service,
mounts and credentials environment. From that folder:

```text
docker compose run --rm evaluate plan roundtrip --deployment /evaluation/deployment --config /evaluation/configs/MGridICSA.roundtrip.json
docker compose run --rm evaluate run roundtrip --deployment /evaluation/deployment --config /evaluation/configs/MGridICSA.roundtrip.json --output /evaluation/results
```

The service runs only when requested. Deploy does not start an evaluation.

## Roundtrip settings

See `examples/MGridICSA.roundtrip.json`. The versioned envelope contains
`schema_version`, `evaluation`, and implementation-specific `parameters`.

| Parameter | Meaning |
| --- | --- |
| `mode` | `storage` (default) or `ingestion` |
| `target` | Full logical component path from the applied hierarchy |
| `property` | Deployed telemetry property to write and read |
| `value` | A value compatible with the deployed property type |
| `targets` | List of `{target, property, value}` objects instead of a single target/property/value |
| `samples` | Number of measured cycles per target; default 100 |
| `warmup` | Number of excluded warmup cycles per target; default 10 |
| `concurrency` | Maximum simultaneous roundtrip cycles across all targets; default 1 |
| `timeout_seconds` | Monotonic deadline for each entire cycle; default 10 |
| `poll_interval_seconds` | Delay after an unsuccessful read; default 0.05 |
| `request_timeout_seconds` | Individual SDK read timeout; default 10 |

Storage invokes the persister synchronously, then the existing hot-reader.
Ingestion uses the IoT Data HTTPS Publish API with QoS 1, then reads through the
same hot-reader. It therefore includes the deployed dispatcher, processor, and
persister path. Both modes can trigger the twin's configured business rules.
The supplied MGridICSA example measures seven telemetry devices: battery
`totalCapacity`, PV `output`, and `consumption` on each of the five chargers.
These property names do not match the deployed `power` conditions. The controller
has no telemetry properties, and generated constant components are excluded.

`examples/VPP.roundtrip.json` covers the saved 100-household VPP
deployment: Grid telemetry and the Sensor and BESS of every household. It uses
storage mode, 5 measured cycles per device, no warmup cycles, and concurrency 10.
The 201 devices produce 1005 measured messages in total. Inspect its offline plan:

```powershell
python -m digital_twin_evaluation plan roundtrip --deployment ../reproduce/work/VPP/output --config examples/VPP.roundtrip.json
```

For multiple devices, set `parameters.targets` to a non-empty list. Each entry
must contain exactly `target`, `property`, and `value`; each device may appear
once. Put shared mode, sample counts, warmup counts, and timeouts alongside the
list. All targets are validated before AWS clients are created. With
`concurrency: 1`, devices run sequentially in the configured order. They share
one backend client. A failed
device remains in the report and does not skip the remaining devices. The
single-target format remains supported.

The client starts its monotonic timer before sending and stops only after a
decoded response matches both the sent timestamp and value. Each cycle gets a
distinct UTC millisecond timestamp per device within the run.
Use one evaluation process per target and record background traffic when comparing
runs. Reading uses the exact timestamp range and does not scan the whole history.

Set `parameters.concurrency` above 1 to send messages in parallel. The supplied
example uses 20: at most 20 complete write/read cycles are active across all
devices together. Both storage and ingestion use their existing per-message
paths. Each worker sends one message and polls for that message's exact timestamp
and typed value. Increasing concurrency increases offered load.

Parallel runs complete all warmup cycles before measured cycles begin. Targets
are scheduled in turn, and pending work is limited to the worker count rather
than queuing the entire run. A scheduler assigns distinct millisecond timestamps
before submission, even when messages use the same device and value. Raw CSV
rows are ordered by submission sequence; completion order can differ.

AWS clients are constructed before sample timing, including sequential ingestion
with no warmup. In parallel runs, clients are ready before workers start. Their
connection pool is sized for the worker count. This follows the official
[Boto3 client threading guidance](https://docs.aws.amazon.com/boto3/latest/guide/clients.html#multithreading-or-multiprocessing-with-clients)
and [Botocore connection-pool configuration](https://docs.aws.amazon.com/botocore/latest/reference/config.html).

The service preserves the deployed reader's consistency behavior. A stale or
missing result is polled until visible or until the deadline. An in-flight SDK
request may finish after the cycle deadline and is then counted as a timeout.
SDK retries are disabled so retries cannot silently change the measurement.
The service does not infer cold starts or alter provisioned concurrency.

## Results

Results are written to `results/<twin>/<run-id>/`:

- `summary.json`: schema version, effective plan, applied state fingerprint,
  Python/SDK versions, counts, errors, and p50/p95/p99/min/max.
- `measurements.csv`: every warmup and measured cycle, its timestamp/value,
  status, polling attempts, and durations in milliseconds.

For multiple devices, `summary.targets` contains separate counts and percentiles
for each device, and the top-level summary also contains totals across all
devices. CSV rows identify the logical `target`, `property`, and `device_id`.
The seven-device example produces 700 measured cycles and 70 warmup cycles.

`write_ms` is the send/invoke duration. `read_ms` sums reader requests and excludes
polling sleeps. `roundtrip_ms` includes the full cycle, including polling waits.
Percentiles use nearest rank and only successful measured samples. Failed samples
and warmup failures remain visible in counts and raw CSV. Warmup failure alone
does not fail a run whose measured samples all succeeded. Small sample counts
make tail percentiles less representative; the count is always reported.

For parallel runs, `duration_ms` covers warmup and measurement execution.
`measured_duration_ms` covers the measured phase, including scheduling and queue
wait. `successful_samples_per_second` divides successful measured cycles by
that phase's duration. Each sample's `roundtrip_ms` starts inside its worker
immediately before sending and excludes time waiting for a worker slot.

Exit codes: 0 for success or an offline plan, 1 for measured sample failures,
and 2 for invalid configuration or startup failure.

## Resource count

`scripts/resource_inventory.py` counts the resources that exist for a twin and compares them with the allocation formula (paper Figure 6). It reads the account and changes nothing:

```text
uv run --no-project --with boto3 python scripts/resource_inventory.py --twin <twin name> --regions <region>
```

## Add another evaluation

1. Add a module under `digital_twin_evaluation/evaluations/`.
2. Implement `Evaluation.prepare(deployment, parameters)`.
3. Return a `PreparedEvaluation` with `describe()` and `run()` methods.
4. Return the common `RunResult` model from `run()`.
5. Register the implementation in `evaluations.EVALUATIONS`.

The CLI and report writer do not depend on roundtrip internals. Each implementation
owns its parameter validation and execution dependencies. The manager adapter is
the boundary for deployment formats; another state version or provider should
have an explicit adapter rather than a silent fallback.

## Verification

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

Tests use deterministic clocks and local AWS substitutes. They verify exact
correlation, error handling, visibility timeouts, warmup accounting, the SDK
request contract, reports, and registration of another evaluation type. They do
not generate cloud traffic.
