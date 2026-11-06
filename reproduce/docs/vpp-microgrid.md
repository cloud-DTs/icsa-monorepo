# VPP model and scale settings

The VPP model contains one shared Grid, one CW service, and one entity per household
named `Household0001`, `Household0002` and so on. Each household contains
`Sensor : HouseholdEnergySensor` and `BESS : BatteryEnergyStorage`.

The generator defaults to 1000 households. The model in `models/` contains
100 households, the size of the case study. Use `--households 100` to regenerate it.

## Generate the model

From the `reproduce/` folder:

```text
python scripts/generate_vpp_microgrid.py --households 100
```

The default output is:

```text
models/VPPMicrogrid.sysml
```

Maintain component definitions and shared architecture in the source template:

```text
models/VPPMicrogrid.sysml.template
```

Regenerate the model after editing the template. Generation is deterministic,
and increasing the household count preserves existing household names. The
template keeps the `.template` extension, so the parser reads only the generated model.

To generate a smaller model at a separate path:

```text
python scripts/generate_vpp_microgrid.py --households 3 --output generated/VPPMicrogrid.sysml
```

## Multiplicity support

The current `DigitalTwinProfileSysMLv2` parser explicitly rejects multiplicity
on annotated usages in `ModelMapper._has_meta_type`. Its README documents the
same restriction. A household usage with `[1000]` does not expand into 1000
deployable households. `VECTOR_DOUBLE`, `VECTOR_INTEGER`, and `VECTOR_STRING`
describe telemetry values rather than collections of entities or devices.

The generator therefore emits a separate entity usage for each household.
Every usage retains the Sensor and BESS inherited from `HouseholdSite`.

## Architecture and output

Each household has dependencies for reading Grid and actuating its own BESS.
CW has one billing dependency on Grid and an energy-reading dependency on every
household. Dependency names and endpoints are generated together with entity
names.

Dependencies describe architecture; the parser does not turn them into
executable control logic. One explicit mock action tests the MQTT feedback path
for `Household0001.BESS.activePowerKW`.

For 1000 households, the expected parser output is:

| Item | Count |
| --- | ---: |
| Household entities | 1000 |
| All entities, including Grid and CW | 1002 |
| Household Sensor components | 1000 |
| Household BESS components | 1000 |
| Grid telemetry components | 1 |
| All IoT devices | 2001 |
| Telemetry properties | 6002 |
| Architectural dependencies in SysML | 3001 |
| Executable events | 1 |

## MQTT mock strategy

The `mqttProbe` action uses
`code/vpp/mqtt-probe/lambda_function.py`. It receives `powerKW` from
`Household0001.BESS.activePowerKW` and returns the exact input value:

```json
{"mock": true, "action": "mqttProbe", "value": 1.25}
```

The condition compares `activePowerKW` with itself using `EQUAL`. The parser
requires property references for both operands. This mock therefore needs only
the measured property, with no separate threshold or initial-value device.
Run the evaluation with one writer for that property.

MQTT feedback publishes the action result to `VPP/evaluation/feedback`.
The input topic remains `VPP/iot-data`. The evaluator matches the exact
sent value in the reply's `value` field, together with `action: mqttProbe`.

## Parse, deploy and evaluate

The twin name is `VPP`, within the parser's 10-character limit. Follow the steps in
the [README](../README.md) with `TWIN=VPP` and `EVAL_CONFIG=VPP.mqtt.json`, parsing
`/pipeline/input/VPPMicrogrid.sysml`.

`evaluation/VPP.mqtt.json` selects one BESS, 100 measured samples, 10 warmup
samples, and `concurrency: 1`.

## Tests

```text
python -B -m pytest -q -p no:cacheprovider tests
```

Tests cover household counts, unique names, dependency endpoints, preservation
of the existing component definitions, deterministic output, CLI validation, and
exact mock replies. The model with the MQTT strategy was checked with the real
SysML kernel and parser for 100 households: 102 entities, 201 devices and one
event. Existing entity/device IDs and telemetry properties match the saved
deployment. An offline evaluator check matched all 110 mock replies.
