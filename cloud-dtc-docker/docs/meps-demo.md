# MEPSO Federated Twin Demo

## Requirements matrix

The following shared conventions are defined:

- Power is in MW.
- Positive community power means consumption, battery charging, or increased
  demand. Negative power means generation, battery discharging, or reduced
  demand.
- Transformer-substation exchange is positive for import/absorption and
  negative for export/injection.
- Each transformer substation has a 10 MW absolute exchange limit.

## Runtime input contract

All power values are `DOUBLE` values in MW. String values are trimmed and
converted to uppercase by the decision Lambda where noted below. The SysML
model does not enforce string enums, so an unsupported string can be stored
without activating the intended scenario.

### TSO service request

| Attribute          | Accepted/recommended values       | Used by decision | Behaviour                                                                                                                                                |
| ------------------ | --------------------------------- | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `requestedPower`   | Number, normally `>= 0`           | Yes              | Requested service magnitude. Negative, missing, and non-numeric values become `0`.                                                                       |
| `serviceDirection` | `NONE`, `UPWARD`, `DOWNWARD`      | Yes              | Case-insensitive. `UPWARD` reduces demand/exports power; `DOWNWARD` increases demand/imports power. Other values do not activate a TSO service scenario. |
| `serviceType`      | For example `NONE` or `BALANCING` | No               | Stored and forwarded from TSO, but currently does not affect allocation or mode.                                                                         |

Publish the complete request and update `requestedPower` when activating a TSO
scenario. The TSO condition is triggered by `requestedPower`; changing only
`serviceDirection` or `serviceType` is not a reliable way to rerun the
federation.

### DSO substation state

| Attribute       | Accepted/recommended values                           | Used by decision | Behaviour                                                                                                           |
| --------------- | ----------------------------------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------- |
| `voltageStatus` | `NORMAL`, `HIGH_VOLTAGE`; `LOW_VOLTAGE` may be stored | TS1 only         | Only TS1 `HIGH_VOLTAGE` currently activates local voltage support. Other values do not activate a voltage scenario. |
| `exchangePower` | Signed MW                                             | Output only      | Forwarded to Aggregator but not used in allocation. The calculated result is written back here after each decision. |
| `exchangeLimit` | Positive MW                                           | Yes              | Used independently for TS1 and TS2. Missing, zero, negative, or non-numeric values use the default `10 MW`.         |

### EC telemetry

| Attribute       | Unit / values                 | Used by decision   | Behaviour                                                                                                                |
| --------------- | ----------------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| `stateOfCharge` | Battery SoC, normally percent | No                 | Forwarded and stored, but no battery-energy emulator currently updates or consumes it.                                   |
| `batteryPower`  | Signed MW                     | Output only        | Positive means charging; negative means discharging. The calculated decision is written directly back here.              |
| `pvPower`       | MW, normally `>= 0`           | Yes, downward only | EC1/EC2 PV is added to the corresponding battery charging allocation for `DOWNWARD`. Negative PV is treated as `0`.      |
| `dsrPower`      | Signed MW                     | Output only        | Positive means increased demand; negative means demand reduction. The calculated decision is written directly back here. |

Battery and DSR telemetry updates are forwarded to Aggregator for visibility,
but they are deliberately excluded from the portfolio-decision strategy
inputs. This prevents direct result writes from recursively triggering another
decision.

### Current constants and policy limits

| Value                                   | Current setting                | Source / effect                                                                                       |
| --------------------------------------- | ------------------------------ | ----------------------------------------------------------------------------------------------------- |
| TS1 exchange limit                      | `10 MW` default                | Runtime `ts1ExchangeLimit` overrides it when positive.                                                |
| TS2 exchange limit                      | `10 MW` default                | Runtime `ts2ExchangeLimit` overrides it when positive.                                                |
| EC1 battery charge/discharge capability | `10 MW`                        | Present as SysML constants, but the current policy uses scenario-specific allocations capped in code. |
| EC2 battery charge/discharge capability | `10 MW`                        | Present as SysML constants, but the current policy uses scenario-specific allocations capped in code. |
| EC1 DSR allocation                      | Up to `3 MW` in upward service | Hard-coded by the current demonstration policy.                                                       |
| EC2 DSR allocation                      | Up to `1 MW` in upward service | Hard-coded by the current demonstration policy.                                                       |
| TS1 high-voltage response               | Battery `+4 MW`, DSR `+2 MW`   | Limited by the effective TS1 exchange limit.                                                          |

The `substationId`, battery capability, and DSR capability constants are model
metadata, but the Lambda does not currently load them dynamically.

## Attribute usage matrix

| Twin/component          | Attribute                                                     | Current status                                                               |
| ----------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `dtcTSO.serviceRequest` | `requestedPower`, `serviceDirection`                          | Active decision inputs.                                                      |
| `dtcTSO.serviceRequest` | `serviceType`                                                 | Stored/forwarded; unused by decision.                                        |
| `dtcDSO.ts1`            | `voltageStatus`, `exchangeLimit`                              | Active decision inputs.                                                      |
| `dtcDSO.ts2`            | `exchangeLimit`                                               | Active decision input.                                                       |
| `dtcDSO.ts2`            | `voltageStatus`                                               | Stored/forwarded; no policy branch currently uses it.                        |
| `dtcDSO.ts1/ts2`        | `exchangePower`                                               | Decision output destination; incoming value is unused for allocation.        |
| `dtcEC1/2.battery`      | `stateOfCharge`                                               | Stored/forwarded; unused by decision and not emulated.                       |
| `dtcEC1/2.battery`      | `batteryPower`                                                | Direct decision output destination; previous value is unused for allocation. |
| `dtcEC1/2.pv`           | `pvPower`                                                     | Active only in `DOWNWARD` service.                                           |
| `dtcEC1/2.dsr`          | `dsrPower`                                                    | Direct decision output destination; previous value is unused for allocation. |
| `dtcAggreg.decision`    | EC battery/DSR power, TS exchange power                       | Calculated outputs forwarded to EC and DSO twins.                            |
| `dtcAggreg.decision`    | `deliveredPower`, `deliveredServiceDirection`, `decisionMode` | Observable result fields for dashboards.                                     |
| `dtcAggreg.decision`    | `decisionVersion`                                             | Internal `DOUBLE` trigger for every completed decision.                      |

The generated decision uses these output tokens:

| Output attribute            | Possible current values                                                                                                           |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `decisionMode`              | `MONITORING`, `LOCAL_DSO_SUPPORT`, `UPWARD_SERVICE`, `DOWNWARD_SERVICE`                                                           |
| `deliveredServiceDirection` | `NONE`, `UPWARD`, `DOWNWARD`                                                                                                      |
| `deliveredPower`            | Non-negative delivered service magnitude in MW; local DSO support currently reports `0` because it is not a TSO service delivery. |
| `decisionVersion`           | Unix time in milliseconds represented as `DOUBLE`; this is an internal trigger, not a business measurement.                       |

## Valid scenario inputs

| Scenario         | TSO request                                                                        | DSO state                                                  | EC PV telemetry       | Expected result                                                       |
| ---------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------- | --------------------- | --------------------------------------------------------------------- |
| Baseline         | `requestedPower=0`, `serviceDirection=NONE`, `serviceType=NONE`                    | TS1/TS2 `voltageStatus=NORMAL`, positive or omitted limits | EC1/EC2 `pvPower=0`   | All calculated power values `0`, mode `MONITORING`.                   |
| TS1 high voltage | `requestedPower=0`, `serviceDirection=NONE`                                        | TS1 `voltageStatus=HIGH_VOLTAGE`; TS2 `NORMAL`             | Any                   | EC1 battery/DSR `+4/+2`, TS1 exchange `+6`, mode `LOCAL_DSO_SUPPORT`. |
| Upward service   | `requestedPower=12`, `serviceDirection=UPWARD`, optional `serviceType=BALANCING`   | TS1/TS2 `NORMAL`, limits `10` or omitted                   | Any                   | EC1 `-5/-3`, EC2 `-3/-1`, TS exchange `-8/-4`.                        |
| Downward service | `requestedPower=10`, `serviceDirection=DOWNWARD`, optional `serviceType=BALANCING` | TS1/TS2 `NORMAL`, limits `10` or omitted                   | EC1 `3`, then EC2 `2` | EC1 battery `+8`, EC2 battery `+7`, TS exchange `+5/+5`.              |

When switching from TS1 high voltage to a TSO service scenario, set TS1 back
to `NORMAL`; otherwise a zero or invalid TSO request can fall through to the
still-active `HIGH_VOLTAGE` branch.

| Twin        | Owned state / attributes                                 | Inputs                             | Outputs                           | Trigger                                                      |
| ----------- | -------------------------------------------------------- | ---------------------------------- | --------------------------------- | ------------------------------------------------------------ |
| `dtcTSO`    | requested power, service direction, service type         | MEPSO operator/scenario            | complete service request          | `requestedPower` update                                      |
| `dtcDSO`    | TS1/TS2 voltage status, exchange, exchange limit         | DSO telemetry; Aggregator decision | complete state for the changed TS | TS voltage-status update                                     |
| `dtcEC1`    | battery SoC/power, PV power, DSR power, TS1 capabilities | EC1 telemetry; Aggregator decision | battery/PV/DSR state              | each telemetry update                                        |
| `dtcEC2`    | battery SoC/power, PV power, DSR power, TS2 capabilities | EC2 telemetry; Aggregator decision | battery/PV/DSR state              | each telemetry update                                        |
| `dtcAggreg` | federated TSO/DSO/EC inputs; atomic portfolio decision   | all four source twins              | result plus EC1/EC2 power         | any federated input update; `decisionVersion` forwards power |

The Aggregator decision component owns the complete calculated result on one
IoT device. `decisionVersion` then triggers six independent writes: four to the
EC battery/DSR devices and two to the DSO exchange devices.

## Federation topology

```text
dtcTSO ───────────────┐
dtcDSO (TS1, TS2) ────┤
dtcEC1 (bat, PV, DSR) ├──> dtcAggreg inputs
dtcEC2 (bat, PV, DSR) ┘             │
                                    v
                           portfolio decision
                                    │
                         decisionVersion update
                       ┌──────┼───────────┐
                       v      v           v
                EC1 battery/DSR  EC2 battery/DSR  DSO TS1/TS2 exchange
```

The tracked federation template is
`pipeline/fed-sysml/input/fedtwin.mepso.example.json`. It contains nine input
push strategies, one portfolio-decision strategy, and six direct telemetry
strategies.

The portfolio strategy collects only the seven values consumed by the decision
logic. Each direct telemetry strategy forwards one calculated power value to
the corresponding battery, DSR, or DSO substation IoT device. Splitting these
writes is required because one federation feedback message addresses one
`iotDeviceId`. It also keeps the generated Lambda `PARAMETERS` environment
variable below AWS Lambda's 4 KB aggregate environment-variable limit.

The demo has no EC actuator/emulator. Therefore the calculated battery and DSR
power is written directly to `batteryPower` and `dsrPower`; there are no
intermediate setpoint attributes. `stateOfCharge` remains independent because
updating it correctly requires battery capacity and elapsed time.

`decisionVersion` is a `DOUBLE` because the SysML v2 profile does not export a
`LONG`, while a Unix timestamp in milliseconds exceeds the 32-bit `INTEGER`
range. Millisecond timestamps remain exactly representable as doubles below
`2^53`, allowing TwinMaker to read the trigger value and fire all six direct
telemetry writes.

## Expected scenario results

| Time  | Primary update                                                                                                                                 | EC1 battery / DSR | EC2 battery / DSR | TS1 / TS2 exchange | Mode                |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | ----------------- | ------------------ | ------------------- |
| 00:00 | baseline state, to trigger set dtcTSO => serviceRequest => requestedPower to 0                                                                 | 0 / 0             | 0 / 0             | 0 / 0              | `MONITORING`        |
| 02:00 | set dtcDSO => ts1 => voltageStatus `HIGH_VOLTAGE`                                                                                              | +4 / +2           | 0 / 0             | +6 / 0             | `LOCAL_DSO_SUPPORT` |
| 06:00 | set dtcDSO => ts1 => voltageStatus `NORMAL`; dtcTSO => serviceRequest - requestedPower to 12 and serviceDirection to `UPWARD`                  | -5 / -3           | -3 / -1           | -8 / -4            | `UPWARD_SERVICE`    |
| 12:00 | dtcEC1 => pv => pvPower to 3; dtcEC2 => pv => pvPower to 2; dtcTSO => serviceRequest - requestedPower to 10 and serviceDirection to `DOWNWARD` | +8 / 0            | +7 / 0            | +5 / +5            | `DOWNWARD_SERVICE`  |

## Local generation and deployment order

1. Copy `.env.example` to `.env` and supply AWS credentials securely.
2. Convert and deploy `dtcTSO`, `dtcDSO`, `dtcAggreg`, `dtcEC1`, and
   `dtcEC2` individually with `continue sysml-v2 <file>`.
3. Copy `fedtwin.mepso.example.json` to the ignored `fedtwin.json` and
   `brokerConfig.example.json` to the ignored `brokerConfig.json`.
4. Run `python3 scripts/resolve_mepso_federation_targets.py`. This resolves the
   seven generated device IDs from the five saved deployments and renders the
   three ignored federation Lambda entrypoints.
5. Run `continue fed-sysml`, `fed terraform plan`, and
   `fed terraform apply`.
6. Publish scenario state through the five saved twin simulators in the order
   shown above and verify the Aggregator decision fields.

Do not commit `.env`, resolved Lambda sources, manager deployment snapshots,
or generated Terraform/state.
