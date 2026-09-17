# Microgrid Federated Twin Demo

Guide for StefiGroz's five-twin Microgrid example. Use the standard
`docker-compose.yaml` and `pipeline/fed-sysml/output` for federation output.
Keep separate ZIP backups when switching between Microgrid and MEPSO.

## Models and federation topology

All models are in `pipeline/digital-twin-profile-sysml-v2/input/`.

| Model              | Role                                                               |
| ------------------ | ------------------------------------------------------------------ |
| `dtcWeather.sysml` | Hourly solar forecast; read by the PV strategy.                    |
| `dtcPV.sysml`      | Converts `hours_cycle` and the forecast into PV production.        |
| `dtcGrid.sysml`    | Publishes green-energy percentage, available power, and price.     |
| `dtcBattery.sysml` | Collects inputs, decides power allocation, and updates its charge. |
| `dtcCharger.sysml` | Publishes EV connection state and receives power allocation.       |

The template `pipeline/fed-sysml/input/fedtwin.microgrid.example.json` defines
six strategies: Weather lookup, PV-to-Battery production, Grid-to-Battery green
percentage and maximum power, Charger-to-Battery connection state, and the
Battery charging decision. The decision reads the Grid price and writes
Charger power plus Battery charge/grid draw.

Deploy Weather even though it has no strategy action. The legacy
`dtc-2-pv.sysml`, `dtc-2-bat.sysml`, and `fedtwin.example.json` belong to a different example.

## Runtime input contract

Power is in **kW**, capacity in **kWh**, and charge in **percent**.
Positive Battery power means charging; negative means discharging.

| Twin/component            | Attribute                 | Demo value / behaviour                                                                                                                               |
| ------------------------- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dtcBattery.storage`      | `charge`                  | Publish `50` once before testing; the decision then updates it.                                                                                      |
| `dtcGrid.sensor`          | `maxPower`                | Publish `25`; this is a runtime input, not an automatic constant.                                                                                    |
| `dtcGrid.sensor`          | `currentElectricityPrice` | Optional. Missing or non-positive price has the same effect as `0.25` EUR/kWh. Higher prices reduce available Grid power in the green-energy branch. |
| `dtcGrid.sensor`          | `greenEnergyPercentage`   | `70` uses Battery/PV; `80` uses Grid/PV. The threshold is `75`.                                                                                      |
| `dtcPV.panel`             | `hours_cycle`             | Integer `0`–`23`; selects the hourly solar forecast.                                                                                                 |
| `dtcCharger.chargerState` | `isPlugged`               | String `true` or `false`.                                                                                                                            |

Current limits: PV `10 kW`, EV `22 kW`, Battery charge/discharge `10 kW`,
Battery capacity `200 kWh`. Battery cannot discharge at charge `<=20%` or
charge further at `100%`. Grid `gridLimit` is unused by the decision.

Results are stored in `dtcPV.panel.production`,
`dtcCharger.chargerState.actChargeEV` / `actBatteryCharge`, and
`dtcBattery.storage.charge` / `gridPower`.

## Local generation and deployment order

Run PowerShell commands from the repository root. Configure AWS credentials
and region in `.env`, with `SIMULATOR_MOCK_AWS=false`.

1. Start the orchestrator:

   ```powershell
   uv run python run_pipeline.py
   ```

2. In its terminal, convert and deploy all five twins. Decline federation until
   all deployments are saved under `pipeline/digital-twin-manager/deployments/`.

   ```text
   continue sysml-v2 dtcWeather.sysml
   continue sysml-v2 dtcGrid.sysml
   continue sysml-v2 dtcBattery.sysml
   continue sysml-v2 dtcPV.sysml
   continue sysml-v2 dtcCharger.sysml
   ```

3. In a separate PowerShell, select the template and resolve Battery device IDs:

   ```powershell
   Copy-Item pipeline/fed-sysml/input/fedtwin.microgrid.example.json pipeline/fed-sysml/input/fedtwin.json
   uv run python scripts/resolve_grid_battery_push_target.py
   uv run python scripts/resolve_grid_battery_maxpower_target.py
   uv run python scripts/resolve_pv_battery_generatedpower_target.py
   uv run python scripts/resolve_charger_battery_plug_target.py
   ```

   Keep the existing `brokerConfig.json`, or create it from
   `pipeline/fed-sysml/input/brokerConfig.example.json` if missing.
   Repeat the four resolvers whenever Battery device IDs change.

4. Ensure `output` contains the matching Microgrid state if resources already
   exist; see [Terraform state backups](#terraform-state-backups). In the orchestrator:

   ```text
   continue fed-sysml
   fed terraform plan
   fed terraform apply
   ```

   Review the plan before confirming apply. Switching `fedtwin.json` alone
   does not switch Terraform state.

5. Complete the two strategies' AWS configuration from PowerShell:

   ```powershell
   uv run --no-project --with boto3 --env-file .env python scripts/federate_pv_weather.py
   uv run --no-project --with boto3 --env-file .env python scripts/federate_battery_charger_decision.py
   ```

   These inject reader coordinates, constants, device IDs, and invoke permissions.
   The orchestrator does not run them automatically. Repeat both after an apply
   that changes these Lambda configurations.

6. Start the simulators in the orchestrator; Weather needs no simulator:

   ```text
   start simulator dtcBattery
   start simulator dtcGrid
   start simulator dtcPV
   start simulator dtcCharger
   ```

## Expected scenario results

First publish Battery `charge=50` and Grid `maxPower=25`.
Wait for these inputs to arrive, then publish the scenario values below.
All rows except baseline assume EV connected and Battery charge between 20% and 100%.
Price can be omitted. If a price above `0.25` EUR/kWh was previously published,
set it to `0.25` to reproduce these results.

| `hours_cycle` | Green energy, % | EV connected | PV, kW | Grid, kW | EV, kW | Battery, kW |
| ------------- | --------------- | ------------ | ------ | -------- | ------ | ----------- |
| `0`           | 70              | `false`      | 0      | 0        | 0      | 0           |
| `5`           | 70              | `true`       | 0      | 0        | 10     | -10         |
| `6`           | 80              | `true`       | 0      | 25       | 22     | +3          |
| `8`           | 80              | `true`       | 2      | 25       | 22     | +5          |
| `12`          | 80              | `true`       | 10     | 22       | 22     | +10         |
| `13`          | 70              | `true`       | 10     | 0        | 20     | -10         |

PV production, green-energy updates, and `isPlugged=true` trigger decisions.
Changing only charge, price, or `maxPower` does not. After these changes or
unplugging EV, repeat `hours_cycle` to recalculate; allow time for federation delivery.

Do not continuously publish the initial `charge` from the simulator. Charge
advances with real elapsed time at **120x speed**, even when `hours_cycle` stays
fixed. At +10 kW, going from 50% to 100% takes about five real minutes.
At hour 12 with a full Battery, the expected result becomes PV `10`, Grid `12`,
EV `22`, Battery `0`. Publish charge `50` once to repeat the earlier state.

## Terraform state backups

After applying changes and before switching demos, archive the active `output`
directory. Run this only while it contains the Microgrid deployment:

```powershell
Compress-Archive -Path pipeline/fed-sysml/output -DestinationPath pipeline/fed-sysml/microgrid-output.zip -Force
```

Use `mepso-output.zip` when saving the MEPSO deployment. Both archives contain
`output/terraform.tfstate` and are ignored by Git. Keep twin deployment snapshots
under `pipeline/digital-twin-manager/deployments/` separately; this ZIP covers federation only.

To switch back, first back up the current demo and move its `output` directory
aside. With `pipeline/fed-sysml/output` absent, restore Microgrid:

```powershell
Expand-Archive -Path pipeline/fed-sysml/microgrid-output.zip -DestinationPath pipeline/fed-sysml
```

Confirm the state is at `pipeline/fed-sysml/output/terraform.tfstate`, select the
matching `fedtwin.json`, and regenerate/plan using step 4. Always build a new
plan after restoring state; do not apply a plan from the ZIP.
ZIP backup/restore changes local files, not AWS resources.

## Troubleshooting

Check CloudWatch `/aws/lambda/<strategyName>_pipeline`, especially
`dtc-BatteryChargerDecisionStrategy_pipeline`: `DIAG inputs` shows the values
actually used, and `DIAG actChargeEV` shows the resulting power split.

| Symptom                                                                   | Cause / fix                                                                                                                                                                                                          |
| ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `EntityAlreadyExists`, with Terraform planning to recreate existing roles | Missing or wrong state. Restore the matching ZIP. If no usable state exists, audit and import the existing resources before planning again.                                                                          |
| Missing environment variables or reader `AccessDenied`                    | Run both `federate_*.py` commands from step 5 after apply.                                                                                                                                                           |
| Feedback contains placeholder or old device IDs                           | Run the four resolvers, rebuild with `continue fed-sysml`, plan/apply, then repeat step 5.                                                                                                                           |
| New `charge=50` is persisted, but the decision still reads old `0`        | The old reader request scanned oldest records first and hit its record limit. Deploy the corrected `_pull` using `orderByTime="DESCENDING"`, `maxResults=1`, and the first returned value; then reinitialize charge. |
| Hour 5 gives no EV power or Battery discharge                             | Ensure `isPlugged=true`, green energy `70`, and charge above `20%`. Missing charge becomes zero.                                                                                                                     |
| Green energy is `80`, but `gridMaxPower=0`                                | Publish Grid **`maxPower=25`**, then retrigger. Check delivery to `dtcBattery.externalInputs.maxPower`; filling the simulator field alone does not publish it.                                                       |
| Hour 12 gives Battery `0`, Grid `12`, EV `22`                             | Battery is full. Publish charge `50` once and retrigger; expect Battery `+10` and Grid `22` until full again.                                                                                                        |
| Changing an input has no immediate effect                                 | Charge, price, and max power alone do not trigger the decision. Repeat `hours_cycle` after the input is stored.                                                                                                      |

Audit generated federation resources without modifying AWS:

```powershell
uv run --no-project --with boto3 --env-file .env python scripts/audit_federation_resources.py --directory pipeline/fed-sysml/output
```

If state is unavailable, back up the current output and import the matching
IAM roles, inline policies, Lambda functions, and SSM parameters. For example:

```powershell
docker compose -f docker-compose.yaml --profile pipeline run --rm -T --entrypoint terraform fed-sysml -chdir=/pipeline/output import aws_iam_role.dtc-GridBatteryPushStrategy_pipeline_role dtc-GridBatteryPushStrategy_pipeline-role
```

Import changes Terraform state. Recover all matching resources, not only the
first conflicting role, then create and review a fresh plan before apply.
