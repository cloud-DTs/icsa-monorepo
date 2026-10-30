# Digital twin evaluation service

## MQTT to TwinMaker visibility extension

Add the registered type `mqtt-twinmaker`. Publish a fresh unique DOUBLE over real
MQTT to the deployed twin topic. Poll native TwinMaker `GetPropertyValueHistory`
using the applied workspace/entity/component binding until both the sent UTC
timestamp and value match. Keep one writer, one target and concurrency 1. Do not
require or subscribe to a processing-feedback topic. Do not bypass TwinMaker with
a direct reader Lambda call, and do not count PUBACK as success.

Use one client monotonic timer from before publish to the verified API response.
Exclude setup, preserve warmup/failure records, and compute percentiles only from
successful measured samples. Keep API read time, polling attempts, response
timestamp/value, and optional PUBACK timing in the report. Match ISO8601 timestamps
across timezone/fraction formatting while preserving nanosecond differences.
Check each history page before requesting another one. Stop pagination on the
first matching timestamp and value, and check the deadline between pages.
Handle SDK errors, connection loss and late reads explicitly.
Bound SDK calls and polling; a synchronous in-flight read may overrun the cycle
deadline but must not become a successful sample after that deadline.

Provide offline plans and separate CheckWatt/MGridICSA pipeline examples. This
metric reports observed TwinMaker API availability; it does not claim Grafana
datasource or panel-render latency. Provisioning and AWS benchmark traffic remain
outside the implementation change.

## MQTT processing extension

Implement a separate `mqtt` evaluation for client MQTT -> existing processing
feedback -> client MQTT. The selected first scenario is MGridICSA charger1 power
through Balance. Provisioner source and deployed resources are outside this
change. Resolve feedback from applied config_events.json. Correlate an exact
unchanged input DOUBLE from a configurable path in the reply. Generate a unique
random input value per cycle in an explicit valid range. Require concurrency 1
because current actions can read latest stored values.

Start timing before publish and capture completion in the matched MQTT callback.
Confirm subscription before sending and register the waiter before publish.
Do not count broker acknowledgement, an input-topic echo, a retained reply, an
old value, or a late/duplicate reply as another successful processing cycle.
Report actual received values, errors, and existing warmup/percentile statistics.
Mark connection-interrupted samples and stop publishing after the interruption.
Plan without AWS clients. Discover the endpoint read-only at run startup when
it is not set explicitly. Use signed WSS and existing AWS credential inputs.

For feedback with no echoed input value, this method cannot prove correlation.
A different deployed contract is then needed. CheckWatt has no supplied return
chain. The MGridICSA Balance handler is a mock; receiving its result confirms
that processing path, not execution by a physical actuator.

## Objective and first slice

Implement an independent Python service in `digital-twin-evaluation`, next to
`cloud-dtc-docker`. Run repeatable evaluations against an already deployed twin.
The first evaluation is roundtrip. New evaluation types register a separate
implementation without changing the CLI, deployment adapter, or report writer.

The user authorized implementation while clarification continues. This document
records the first implementation slice and the decisions it makes explicit.

## Input decision

Use the manager's **applied state**, not the current staging input or SysML.
The adapter accepts a saved deployment directory and reads only these files:

- `output/.digital-twin-manager-state/metadata.json`;
- `output/.digital-twin-manager-state/configs/config.json`;
- `output/.digital-twin-manager-state/configs/config_hierarchy.json`;
- `output/.digital-twin-manager-state/configs/config_iot_devices.json`.

The state supplies the deployed twin name, AWS region, entities, device bindings,
and property types. The adapter implements the manager's version 1 AWS naming
contract. Reject missing state, unknown versions, ambiguous targets, and mismatched
twin names. Do not silently fall back to un-applied input. Do not read credentials
from deployment files. Credentials use the standard AWS SDK credential chain.
SysML is a design input and does not identify deployed resources reliably.

Evaluation settings are a separate, versioned JSON object:

```json
{
  "schema_version": 1,
  "evaluation": "roundtrip",
  "parameters": {
    "mode": "storage",
    "target": "MicroGrid.pv.pV1",
    "property": "output",
    "value": 12.5,
    "samples": 100,
    "warmup": 10,
    "timeout_seconds": 10,
    "poll_interval_seconds": 0.05
  }
}
```

## Interfaces and structure

- `deployment.py`: manager state -> immutable deployment and target models.
- `contracts.py`: common models, clock, backend and evaluation protocols.
- `config.py`: validate the common evaluation envelope.
- `evaluations/`: registry and implementations; roundtrip owns its parameters.
- `aws.py`: synchronous Lambda calls, IoT publishing, reader response decoding.
- `reporting.py`: common versioned JSON report and raw CSV measurements.
- `cli.py`: `list`, offline `plan`, and explicit `run` commands.
- `tests/`: pytest tests with deterministic clocks and local AWS substitutes.

The first interface is a batch CLI container, consistent with the pipeline.
An HTTP interface can later call the same application interfaces if requested.

```python
class Evaluation(Protocol):
    def prepare(self, deployment: Deployment, parameters: dict) -> PreparedEvaluation:
        ...
```

Each prepared evaluation describes its plan and produces a common RunResult.
Use plain dataclasses, explicit exceptions, small modules, and no dynamic imports
from configuration. No dependency on the deployer's Python package.

## Roundtrip behavior

Support storage (synchronous persister -> DB -> synchronous reader) and ingestion
(IoT publish -> existing ingestion chain -> synchronous reader). The user selected
both modes with storage as default. The pipeline uses an explicit evaluation
command; it does not generate traffic on deploy by default.

Generate a unique UTC millisecond timestamp for every record per device within a run. Start the
client monotonic timer before sending. Stop only after decoding a reader response
whose timestamp and typed value match the sent record. Query the exact time range.
Record failed writes, reader errors, and visibility timeouts rather than treating
them as successes. A polling deadline bounds retries; an in-flight SDK call can
finish after it. SDK calls have explicit connection/read timeouts and no hidden
automatic retries. Warmup records remain in raw output but do not enter measured
sample percentiles. Preserve zero and negative numeric values.

Reports include run ID, UTC time, source fingerprint, effective plan, sample
counts, failure counts, p50/p95/p99, polling attempts, write/read/roundtrip times,
and raw sample statuses. State the percentile method. Do not infer cold starts
from the first request or subtract client and server wall clocks.

## Pipeline integration

Add a Docker Compose service under profile `evaluation`, with the sibling source
as its build context, a read-only saved deployment mount, a read-only evaluation
config mount, and a writable report mount. Add commands:

```text
plan evaluation roundtrip MGridICSA [config-file]
evaluate roundtrip MGridICSA [config-file]
```

The default config is `pipeline/digital-twin-evaluation/input/MGridICSA.roundtrip.json`.
Results go under `pipeline/digital-twin-evaluation/output/<twin>/<run-id>/` and are
ignored by Git. Preserve the existing deployment and command behavior.

## Commands

```text
python -m digital_twin_evaluation list
python -m digital_twin_evaluation plan roundtrip --deployment ../cloud-dtc-docker/pipeline/digital-twin-manager/deployments/MGridICSA --config examples/MGridICSA.roundtrip.json
python -m digital_twin_evaluation run roundtrip --deployment <saved-deployment> --config <evaluation.json> --output results
python -m pytest -q -p no:cacheprovider
docker build -t digital-twin-evaluation:local .
```

## Boundaries and acceptance

- Implement and test the service and pipeline integration now.
- Run offline planning against the real saved MGridICSA state.
- Verify roundtrip behavior with local substitutes and deterministic clocks.
- Build and exercise the CLI container if Docker is available.
- Do not send evaluation traffic to AWS merely to verify implementation.
- Do not change deployed functions, schemas, or credentials.
- Do not commit generated state, credentials, reports, or unrelated user changes.
- Real AWS evaluation remains an explicit operator command.

## User decisions

1. Both roundtrip modes; storage is the default.
2. A separate command after deploy; start only when requested.
3. A CLI in Docker, consistent with the existing pipeline tools.

## Multiple telemetry devices

Support optional `parameters.targets`, a non-empty list of
`{target, property, value}` entries, instead of the single-target fields. Keep
the single-target format compatible. Validate the complete list before AWS
access and reject repeated device IDs. Apply shared sample and warmup counts
to every target. Execute devices sequentially through one backend instance.

Return one run and report with combined statistics, per-device counts and
percentiles in `summary.targets`, and target/property/device ID on each raw CSV
row. A device failure must not skip later devices.

The user selected the seven MGridICSA telemetry devices: battery, PV, and five
chargers. Exclude the empty controller and generated constant components.

## Parallel roundtrip execution

Add optional positive integer `parameters.concurrency`, default 1. Keep existing
single-target and multi-target configs sequential when it is omitted. For a
parallel run, cap all active cycles and pending futures with one shared worker
limit. Schedule devices in turn, finish the entire warmup phase before starting
measurements, and preserve a separate result for every cycle.

Allocate unique UTC millisecond timestamps per device on the scheduler thread.
Create AWS clients before worker threads and size their HTTP connection pools
for concurrency. Keep retries disabled and preserve each cycle's deadline,
exact timestamp/value validation, error statuses, and latency units.

Keep CSV in submission order, combined and per-device summaries, and add total
duration, measured-phase duration and successful measured cycles per second.
Per-cycle latency starts immediately before sending, excluding worker queue
wait. Configure the MGridICSA example and pipeline config with concurrency 20.
