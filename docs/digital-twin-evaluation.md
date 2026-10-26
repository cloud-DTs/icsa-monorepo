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

Devices run sequentially, with 10 warmup cycles and 100 measured cycles per
device: 70 warmup cycles and 700 measured cycles in total. All targets are
validated against applied state before any AWS call. These properties do not
match the deployed `power` conditions. The controller has no telemetry
properties, and generated constant components are excluded.

The single-target `target` / `property` / `value` format remains supported.

## Commands

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
For multiple devices, `summary.targets` provides separate counts and percentiles
per device. CSV rows include `target`, `property`, and `device_id`. A failed
device remains in the report while the evaluator continues with the others.
The evaluator checks the exact sent timestamp and value. It does not count a
successful API submission or an older database record as a completed roundtrip.

The reader's deployed consistency behavior is preserved. The full roundtrip
includes polling waits; `read_ms` reports the sum of reader calls. Percentiles
exclude failures and warmup samples, while their counts and raw rows remain in
the report. Cold starts are not inferred from call order.

The service has its own CLI and tests. New evaluations implement the common
evaluation interface and register under a new type name. The pipeline command
passes that type through; adding a type does not require another command handler.
