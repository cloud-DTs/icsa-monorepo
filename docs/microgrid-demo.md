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

Current limits: PV `10 kW`, EV `22 kW`, Battery charge/discharge `10 kW`,
Battery capacity `200 kWh`. Battery cannot discharge at charge `<=20%` or
charge further at `100%`. These limits and the Weather hourly forecast come from
the deployed model constants; do not publish them from the simulator. Grid
`sensor.maxPower=25` is a separate **runtime input**, not one of these constants.

### Values you publish

Use these inputs after federation configuration is complete. At the start of
**every demo session**, send fresh initial values even if the twins are already
deployed. The Battery decision reads only the last **24 hours** of telemetry;
readings from an earlier rehearsal may no longer be available to it.

| Twin/component | Attribute | Value to set | When / how often to publish |
| --- | --- | --- | --- |
| `dtcBattery.storage` | `charge` | `50` percent | **Once at the start**, then stop this simulator row. Send again only to reset the experiment, for example after reaching the reserve or full charge. The decision updates it afterwards. |
| `dtcGrid.sensor` | `maxPower` | `25` kW | **Once at the start of each session**; again if you change the available power. Keep the row stopped afterwards. Required for scenarios 3–5. |
| `dtcGrid.sensor` | `currentElectricityPrice` | `0.25` EUR/kWh | Once at the start is recommended to replace any earlier high price. Repeat only when demonstrating a price change. Missing or non-positive price has the same effect as `0.25`; a higher price reduces Grid use. |
| `dtcGrid.sensor` | `greenEnergyPercentage` | `70` or `80`, as listed below | Publish for the first scenario and whenever the value changes. Stop the row after delivery; repeating the same value is not needed. `70` selects Battery/PV; `80` selects Grid/PV. |
| `dtcCharger.chargerState` | `isPlugged` | String `false` for scenario 1; `true` for scenarios 2–6 | Publish at the start and on each connection-state change, then stop the row. No need to repeat `true` between scenarios 2–6. |
| `dtcPV.panel` | `hours_cycle` | `0`, `5`, `6`, `8`, `12`, `13`, in scenario order | Publish each scenario's hour **after the other inputs have arrived**. For a live display of changing charge, keep publishing that same hour about **every 10 seconds**. Repeat it after changing charge, price, maxPower, or unplugging the EV. |

For this short demo, `charge`, `maxPower`, and price do not need a continuous
simulator stream. If a session lasts beyond the 24-hour lookup window, refresh
the unchanged Grid inputs and Charger connection state too. Reinitializing charge
is a deliberate reset, not a periodic refresh of the value `50`.

### Simulator controls and update interval

Filling a field does not send a message. Each attribute has its own **Start/Stop**
button; starting the simulator container only opens the UI.

- For a fixed numeric value, select `uniform` and set **min=max**: `50` for charge,
  `25` for Grid maxPower, `0.25` for price, `70`/`80` for green energy, or the chosen
  hour for `hours_cycle`.
- For `isPlugged`, select `fixed_list` and enter a single value, `true` or `false`,
  without quotation marks. Do not enter both values in the list.
- To send an initial value, start its row, confirm a successful publication, then
  stop it. The UI has no separate send-once button. Confirm delivery in the stored
  data or federation logs before moving on; a successful publish alone does not
  mean the federation has finished processing it.
- For the repeated PV input, use **SimTime(in sec) = 10** and keep only the
  `hours_cycle` row running. Stop that row before editing its hour, then restart
  it. Use `uniform` with equal limits for the numbered scenarios: `cycle` mode
  advances the hour on every publication and will move past the chosen scenario.

Ten seconds is the simulator publication interval, not a guaranteed end-to-end
delivery time. Wait for the matching decision inputs and outputs before judging
a scenario. Stop `hours_cycle` as well if you only want one settled result.

### Values written by federation

**Keep the simulator rows for these properties stopped.** Publishing them
manually can overwrite the calculated result or bypass the twin that supplies it.
The one exception is the initial/reset value of Battery `charge` described above.

| Destination | Property | Source / when it updates |
| --- | --- | --- |
| `dtcPV.panel` | `production` | PV/Weather federation calculates PV `maxPower × forecast percentage / 100` after each `hours_cycle` publication. |
| `dtcBattery.externalInputs` | `generatedPower` | Forwarded automatically from PV `production`. |
| `dtcBattery.externalInputs` | `greenEnergyPercentage` | Forwarded automatically from Grid `sensor.greenEnergyPercentage`. |
| `dtcBattery.externalInputs` | `maxPower` | Forwarded automatically from Grid `sensor.maxPower`. Set `25` on **Grid**, not on Battery. |
| `dtcBattery.storage` | `isPlugged` | Forwarded automatically from Charger `chargerState.isPlugged`. Set the connection state on **Charger**, not on Battery. |
| `dtcCharger.chargerState` | `actChargeEV`, `actBatteryCharge` | Calculated on each Battery decision. `actBatteryCharge` is signed power: positive charges Battery, negative discharges it. |
| `dtcBattery.storage` | `charge`, `gridPower` | Each decision updates Battery charge and the actual Grid power draw. Grid input `maxPower` is the available limit; output `gridPower` is the power actually used. |

Also leave Grid `sensor.gridLimit`, Battery `storage.chargingStatus`, and Battery
`externalInputs.electricityPrice` stopped. The current decision does not use those
fields, and the federation does not populate the latter two. It reads the price
directly from Grid `sensor.currentElectricityPrice`. Weather requires no simulator:
the PV federation reads its deployed hourly forecast constants.

These automatic updates require the federated workflow; the independent twins'
local placeholder actions do not calculate this power allocation.

## Presentation: four twins beforehand, Charger live

Run PowerShell commands from the repository root. Configure AWS credentials
and region in `.env`, with `SIMULATOR_MOCK_AWS=false`. Federation helpers load
this file automatically; existing process environment variables take precedence.

1. Before the presentation, install dependencies and select Microgrid:

   ```powershell
   uv sync --locked
   Copy-Item pipeline/fed-sysml/input/fedtwin.microgrid.example.json pipeline/fed-sysml/input/fedtwin.json
   uv run python run_pipeline.py
   ```

   Keep the existing `brokerConfig.json`, or create it from
   `pipeline/fed-sysml/input/brokerConfig.example.json` if missing. Dependencies
   include `boto3` and `python-dotenv`; no package installation is needed on stage.

2. In the orchestrator, convert and deploy the first four twins. Choose deploy
   for each model and decline federation at this point:

   ```text
   continue sysml-v2 dtcWeather.sysml
   continue sysml-v2 dtcGrid.sysml
   continue sysml-v2 dtcBattery.sysml
   continue sysml-v2 dtcPV.sysml
   fed prepare
   ```

   `fed prepare` runs the four selected resolvers using Battery's saved device
   IDs. Charger is not needed yet, including for the Charger-to-Battery resolver:
   its target device belongs to Battery. This optional command only prepares
   local Lambda sources; it does not generate Terraform or contact AWS.

3. During the presentation, deploy the fifth twin:

   ```text
   continue sysml-v2 dtcCharger.sysml
   ```

   Choose deploy. All five deployment snapshots must now exist under
   `pipeline/digital-twin-manager/deployments/`. Decline automatic federation if
   you want to enter the commands in the next step explicitly.

4. Ensure `output` contains the matching Microgrid state if resources already
   exist; see [Terraform state backups](#terraform-state-backups). Then run:

   ```text
   continue fed-sysml
   fed terraform apply
   ```

   Generation checks the required deployment files, including passive Weather,
   and reruns the four resolvers before fed-sysml packages their source. If
   Battery IDs changed after `fed prepare`, this picks up the new IDs.

   `fed terraform apply` creates a fresh plan and asks for confirmation. After
   a successful apply, the orchestrator automatically runs both selected
   `federate_*.py` helpers. Wait for `Federation configuration complete.` before
   sending simulator events. You can run `fed terraform plan` separately to
   inspect changes. Switching `fedtwin.json` alone does not switch Terraform state.

5. Start the simulators in the orchestrator; Weather needs no simulator:

   ```text
   start simulator dtcBattery
   start simulator dtcGrid
   start simulator dtcPV
   start simulator dtcCharger
   ```

   Follow [Values you publish](#values-you-publish) to initialize the inputs.
   Start only the required attribute rows; leave calculated properties stopped.

For a normal deployment, deploy all five twins in advance and follow step 4.
No separate script commands are required in either workflow.

## Automatic federation preparation and configuration

The registry in `scripts/orchestrator/federation_hooks.py` selects helpers by
`fedTwins[].newStrategies[].name`. Unregistered strategies run without these
helpers; selecting another use case does not run the Microgrid configuration.

| Strategy | Before generation | After successful apply |
| --- | --- | --- |
| `dtc-GridBatteryPushStrategy` | `resolve_grid_battery_push_target.py` | — |
| `dtc-GridBatteryMaxPowerStrategy` | `resolve_grid_battery_maxpower_target.py` | — |
| `dtc-PVBatteryGeneratedPowerStrategy` | `resolve_pv_battery_generatedpower_target.py` | — |
| `dtc-ChargerBatteryPlugStrategy` | `resolve_charger_battery_plug_target.py` | — |
| `dtc-PVWeatherStrategy` | Validate local Weather/PV inputs | `federate_pv_weather.py` |
| `dtc-BatteryChargerDecisionStrategy` | Validate local Grid/Battery/Charger inputs | `federate_battery_charger_decision.py` |

The last two helpers add reader coordinates, constants, device IDs, and invoke
permissions to the federation Lambdas. They run after every successful apply,
including one with no Terraform changes. Matching environment values and IAM
policies are left alone. Plan, cancelled/failed apply, and destroy do not run
AWS configuration helpers.

`output/federation-hooks.json` records the selected helpers, fingerprints of
their inputs and generated artifacts, and whether Terraform was applied. Changed
configurations, deployment files, or generated code require `continue fed-sysml`
and a fresh plan/apply. Older outputs without this manifest must also be regenerated.

If Terraform succeeds but a configuration helper fails, resources remain deployed
and the workflow reports incomplete configuration. Fix the reported cause and run:

```text
fed configure
```

This retries only the selected configuration helpers; it does not reapply Terraform.
If inputs changed, regenerate and apply instead. Configuration still updates AWS
outside Terraform, so the automatic post-apply step is required on subsequent applies.
Direct `federate_*.py` execution remains available for troubleshooting; `--check`
validates local deployment inputs without AWS calls.

## Expected scenario results

1. Stop rows left running from a previous session. Publish Battery `charge=50`,
   Grid `maxPower=25`, and preferably Grid `currentElectricityPrice=0.25`, following
   [the simulator controls above](#simulator-controls-and-update-interval).
   Wait for charge to be stored and maxPower to reach Battery. Stop these rows.
2. Set the scenario's green percentage and Charger connection state. Wait for
   them to reach Battery, then send the selected PV hour. On subsequent scenarios,
   only change the inputs that differ; keep the initialized Grid limit and price.
3. Check `DIAG inputs` in the Battery decision logs: the selected green percentage
   and plug state, `gridMaxPower=25`, and charge above `20%` and below `100%` for
   scenarios 2–6. Compare the outputs only after those inputs have arrived.

The three **Set** columns are simulator inputs. The four **Auto** columns are
results to observe, not values to publish. Price can be omitted if no earlier
high price remains; publishing `0.25` makes the run reproducible.

| Scenario | Set: `hours_cycle` | Set: green energy, % | Set: EV connected | Auto: PV, kW | Auto: Grid, kW | Auto: EV, kW | Auto: Battery, kW |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 — baseline | `0` | 70 | `false` | 0 | 0 | 0 | 0 |
| 2 | `5` | 70 | `true` | 0 | 0 | 10 | -10 |
| 3 | `6` | 80 | `true` | 0 | 25 | 22 | +3 |
| 4 | `8` | 80 | `true` | 2 | 25 | 22 | +5 |
| 5 | `12` | 80 | `true` | 10 | 22 | 22 | +10 |
| 6 | `13` | 70 | `true` | 10 | 0 | 20 | -10 |

PV production, green-energy updates, and `isPlugged=true` trigger decisions.
Changing only charge, price, or `maxPower` does not. After these changes or
unplugging EV, repeat `hours_cycle` to recalculate; allow time for federation delivery.

Do not continuously publish the initial `charge` from the simulator. Each
decision integrates charge using real elapsed time at **120x speed**, even when
repeated `hours_cycle` messages contain the same hour. There is no separate charge
timer: after in-flight events finish, stopping all triggering inputs stops new
updates. The next decision accounts for elapsed time, capped at five real minutes
per calculation. With regular triggers at +10 kW, going from 50% to 100% takes
about five real minutes; at -10 kW, 50% reaches the 20% reserve in about three.
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
| Missing environment variables or reader `AccessDenied`                    | After a successful orchestrator apply, fix the reported AWS/credential issue and run `fed configure`. Allow IAM changes to propagate before retrying events. |
| Feedback contains placeholder or old device IDs                           | Run `continue fed-sysml` and `fed terraform apply`; the resolvers and configuration helpers run automatically. |
| Hook manifest missing or federation input/output changed                  | Select the matching config/state and run `continue fed-sysml`, then `fed terraform apply`. Do not reuse an old plan. |
| New `charge=50` is persisted, but the decision still reads old `0`        | The old reader request scanned oldest records first and hit its record limit. Deploy the corrected `_pull` using `orderByTime="DESCENDING"`, `maxResults=1`, and the first returned value; then reinitialize charge. |
| Hour 5 gives no EV power or Battery discharge                             | Check `DIAG inputs`: `isPlugged=true`, green energy `70`, and charge above `20%`. A missing charge reading in the last 24 hours becomes zero, which the decision then writes back. Publish Battery `storage.charge=50` again, wait for storage, then repeat `hours_cycle=5`. Redeployment is not required. |
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
