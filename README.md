# Cloud DTC Pipeline

This repository runs a Docker Compose pipeline for creating, deploying, and
federating digital twins:

```text
Enterprise Architect project or SysML v2 model
  -> SysML profile converter
  -> digital-twin-manager
  -> optional federation and Terraform
  -> optional simulator and Grafana
```

See [PIPELINE_STATE_DIAGRAM.md](PIPELINE_STATE_DIAGRAM.md) for the execution
states.

## Repository Layout

The canonical inputs are:

```text
demo-code/
  coffee-machine/                          CoffeeTwin actuator Lambda source code
  microgrid/                               Microgrid Lambda source code

pipeline/
  enterprise-architect/
    projects/                              Enterprise Architect source projects
      DemoProject.qea
      Matisse_1.qeax
    input/                                 Optional import source files
      demo_model.xml
    output/                                Generated EA exports (ignored)

  digital-twin-profile-sysml-v1/
    input/                                 Staged EA export (ignored)
    output/                                Generated manager configs (ignored)

  digital-twin-profile-sysml-v2/
    input/                                 Tracked SysML v2 source models
      Battery2.sysml
      CoffeeMachine.sysml
      PV2.sysml
      dtc-s-bat.sysml
      dtc-s-pv.sysml
    run-input/                             Selected run input (ignored)
    output/                                Generated manager configs (ignored)

  digital-twin-manager/
    input/                                 Current staged configs (ignored)
    output/                                Current deployment output (ignored)
    deployments/                           Saved local deployment state (ignored)

  fed-sysml/
    input/
      brokerConfig.example.json            Tracked broker template
      fedtwin.example.json                 Tracked federation template
      brokerConfig.json                    Local broker config (ignored)
      fedtwin.json                         Local federation config (ignored)
      strategyInputs/                      Generated federation input (ignored)
    output/                                Generated Terraform and state (ignored)

  grafana/
    dashboards/                            Tracked dashboard definitions
    provisioning/                          Tracked Grafana provisioning
    grafana.json                           Local runtime state (ignored)
```

Generated directories do not need placeholder files. The orchestrator or
Docker Compose creates them when required.

## Requirements

- Docker Desktop or Docker Engine with Compose.
- Python 3.
- AWS credentials for real deploy, destroy, federation Terraform, or
  CloudWatch-backed Grafana.

Several pipeline images are published for `linux/amd64`. The supplied
`.env.example` selects that platform by default.

## Initial Setup

Run from the repository root:

```powershell
Copy-Item .env.example .env
Copy-Item pipeline/fed-sysml/input/brokerConfig.example.json pipeline/fed-sysml/input/brokerConfig.json
Copy-Item pipeline/fed-sysml/input/fedtwin.example.json pipeline/fed-sysml/input/fedtwin.json
```

Edit `.env` and the two local federation files as needed. They are ignored and
must never be force-added to Git.

The bundled federation template uses:

```text
ConsumptionStrategy2
PV2.production
Battery2.status
```

The MEPSO five-twin demo has a separate tracked federation template and
deployment guide. See [docs/meps-demo.md](docs/meps-demo.md); do not replace the
legacy `fedtwin.example.json` when running the existing MicroGrid example.

For StefiGroz's five-twin Microgrid (Battery, PV, Grid, Charger, Weather), use
`fedtwin.microgrid.example.json` and [docs/microgrid-demo.md](docs/microgrid-demo.md).
The guide includes device-ID resolution, separate Terraform state, and the two
required post-apply enablement scripts.

The `DTP_PATH_MAP` value in `.env.example` maps a legacy absolute path embedded
in the bundled Enterprise Architect model to
`/pipeline/code/microgrid/stopCharging`. It is a model-path translation, not a
path that must exist on the host.

## Start the Pipeline

```powershell
python run_pipeline.py
```

The orchestrator starts:

- `enterprise-architect`;
- `sysml-kernel`;
- a watcher for `pipeline/enterprise-architect/output`.

Open Enterprise Architect at:

```text
http://127.0.0.1:6080
```

Stop the run loop with:

```text
exit
```

Useful launch options:

```powershell
python run_pipeline.py --auto-run
python run_pipeline.py --config path\to\orchestrator_config.json
python run_pipeline.py --remove-infrastructure-on-exit
```

## Enterprise Architect Workflow

The Compose mounts preserve the same directory structure in Wine and on the
host:

| Use            | Wine path                                             | Host path                                |
| -------------- | ----------------------------------------------------- | ---------------------------------------- |
| Project files  | `C:\users\ea\Documents\enterprise-architect\projects` | `pipeline/enterprise-architect/projects` |
| Import sources | `C:\users\ea\Documents\enterprise-architect\input`    | `pipeline/enterprise-architect/input`    |
| Save exports   | `C:\users\ea\Documents\enterprise-architect\output`   | `pipeline/enterprise-architect/output`   |

Open a tracked `.qea` or `.qeax` project and export `.xml`, `.xmi`, or `.sysml`
into the output directory. The watcher detects the export and asks whether to
run the matching converter.

| Export         | Converter                       |
| -------------- | ------------------------------- |
| `.xml`, `.xmi` | `digital-twin-profile-sysml-v1` |
| `.sysml`       | `digital-twin-profile-sysml-v2` |

EA exports are generated artifacts. Do not commit files from
`pipeline/enterprise-architect/output`.

## Direct SysML v2 Workflow

Tracked SysML v2 models live in:

```text
pipeline/digital-twin-profile-sysml-v2/input
```

Run a selected model from the active orchestrator:

```text
continue sysml-v2 Battery2.sysml
continue sysml-v2 CoffeeMachine.sysml
continue sysml-v2 dtc-s-pv.sysml
```

`CoffeeMachine.sysml` references the four deployable actuator handlers under
`demo-code/coffee-machine`. The handlers return `command` and `reason`; the
model forwards that action result to the target actuator through MQTT feedback.

The orchestrator copies the selected file to the ignored `run-input` directory,
runs the v2 converter, and stages the generated manager configs.
Watched SysML v2 exports use the same isolated directory. It is rebuilt with only
the current run's source files. Original models in `input` are preserved for
both values of `clean_stage`.

`dtc-s-pv.sysml` references
`demo-code/microgrid/pv/pv-to-battery-push`. Its Lambda file is a source
template: the battery virtual sensor ID must be injected during deployment
preparation. The placeholder deliberately raises an error if the injection did
not happen, and the generated ID must not be committed.

## Generated Data Flow

| Source                       | Generated local state                                         |
| ---------------------------- | ------------------------------------------------------------- |
| EA export                    | `digital-twin-profile-sysml-v1/input` and `output`            |
| SysML v2 model               | `digital-twin-profile-sysml-v2/run-input` and `output`        |
| Converter output             | `digital-twin-manager/input`                                  |
| Manager input                | `digital-twin-manager/deployments/<Twin>/input`               |
| Manager deploy               | `digital-twin-manager/output` and `deployments/<Twin>/output` |
| Manager plan/apply           | Redeployment state in the matching manager output snapshot   |
| Saved manager outputs        | `fed-sysml/input/strategyInputs`                              |
| Federation config and inputs | `fed-sysml/output`                                            |

Manager deployment output can contain IoT private keys, redeployment state, and
saved plans. Federation output can contain Terraform state, plans, downloaded
providers, account identifiers, and Lambda archives. All of these paths are
ignored.

## Interactive Commands

Type commands in the terminal running `python run_pipeline.py`.

| Command                                | Purpose                                             |
| -------------------------------------- | --------------------------------------------------- |
| `help`                                 | Show available commands.                            |
| `continue sysml-v1`                    | Run the staged v1 converter input.                  |
| `continue sysml-v2 [file]`             | Run a staged v2 model; omit the file for a menu.    |
| `continue digital-twin-manager [name]` | Deploy a saved twin input.                          |
| `plan digital-twin-manager [name]`     | Plan changes to a deployed twin.                    |
| `apply digital-twin-manager [name]`    | Confirm and apply its saved plan.                   |
| `destroy digital-twin-manager [name]`  | Destroy a saved twin deployment.                    |
| `continue fed-sysml`                   | Build federation output from saved manager outputs. |
| `fed prepare`                         | Run selected local federation resolvers before generation. |
| `fed configure`                       | Retry selected configuration helpers after a successful apply. |
| `fed terraform plan`                   | Initialize and plan generated Terraform.            |
| `fed terraform apply`                  | Plan, confirm, and apply generated Terraform.       |
| `fed terraform destroy`                | Confirm and destroy federation resources.           |
| `start simulator [name]`               | Start a local simulator for a saved twin input.     |
| `stop simulator [name]`                | Stop a simulator.                                   |
| `plan evaluation <type> <twin> [config]` | Inspect an evaluation without AWS calls.            |
| `evaluate <type> <twin> [config]`        | Run an evaluation against a saved deployment.       |
| `start grafana`                        | Start local Grafana.                                |
| `stop grafana`                         | Stop local Grafana.                                 |
| `exit`                                 | Stop the watcher.                                   |

## Deploy, Update, and Federate

After conversion, manager configs are available locally in:

```text
pipeline/digital-twin-manager/input
pipeline/digital-twin-manager/deployments/<Twin>/input
```

Deploy or destroy a saved twin:

```text
continue digital-twin-manager Battery2
destroy digital-twin-manager Battery2
```

After changing and regenerating the input for an already deployed twin, create
and apply a redeployment plan:

```text
plan digital-twin-manager Battery2
apply digital-twin-manager Battery2
```

The plan and last-applied manager state are kept under the selected twin's
`deployments/<Twin>/output/.digital-twin-manager-state` snapshot. `apply`
requires a successful `plan` for the same twin and asks for confirmation before
changing AWS resources.

Older deployment snapshots without this state must first be initialized with
the manager's `init-state` command while using the unchanged deployed config.

Before federation, deploy or update every twin referenced by the local
`pipeline/fed-sysml/input/fedtwin.json`, then run:

```text
continue fed-sysml
```

Terraform output is generated under `pipeline/fed-sysml/output`. Use the
interactive Terraform commands instead of committing that directory.

For registered strategies, the orchestrator runs local preparation before
generation and AWS configuration after a successful `fed terraform apply`.
The registry is in `scripts/orchestrator/federation_hooks.py`; selection uses
`newStrategies[].name`. Helpers use the project Python and root `.env` (process
environment values take precedence). Run `uv sync --locked` before the demo.

`fed prepare` can resolve Microgrid Battery targets before Charger is deployed.
`continue fed-sysml` repeats preparation and checks all required twins. The
generated `federation-hooks.json` binds configuration steps to that output and
its deployment inputs. Changed inputs or old Microgrid output without a manifest
require regeneration before plan/apply. If apply succeeds but configuration fails,
fix the error and run `fed configure` to retry without another Terraform apply.
See [the Microgrid presentation workflow](docs/microgrid-demo.md#presentation-four-twins-beforehand-charger-live).

## Digital Twin Evaluation

The sibling `../digital-twin-evaluation` project provides a Docker CLI service
for evaluations of already deployed twins. The first type is `roundtrip`, with
`storage` and `ingestion` modes. Storage is the default. Evaluations run only
when requested:

```text
plan evaluation roundtrip MGridICSA
evaluate roundtrip MGridICSA
```

The service reads the applied manager state and separate experiment settings.
Reports are written under `pipeline/digital-twin-evaluation/output/<Twin>/<run-id>`.
See [the evaluation guide](docs/digital-twin-evaluation.md) for configuration,
measurement boundaries, credentials, and adding evaluation types.

## Simulator and Grafana

Start a simulator for a saved deployment:

```text
start simulator Battery2
```

Simulator ports start at `5000`. Runtime state is written to:

```text
pipeline/digital-twin-manager/deployments/<Twin>/simulator.json
```

Start Grafana:

```text
start grafana
```

Default access:

```text
http://127.0.0.1:3000
admin / admin123
```

The Compose service mounts the tracked files from
`pipeline/grafana/provisioning` and `pipeline/grafana/dashboards` read-only.
The bundled dashboard targets `ConsumptionStrategy2` in `eu-west-1`.

## Configuration

The main orchestrator configuration is `orchestrator_config.json`.

| Field                           | Purpose                                                     |
| ------------------------------- | ----------------------------------------------------------- |
| `digital_twin_name`             | Default name passed to the v1 converter.                    |
| `generated_twin_dir`            | Optional converter output directory override.               |
| `path_maps`                     | Maps model paths to container paths under `/pipeline/code`. |
| `clean_stage`                   | Recreates staging/output directories before a run.          |
| `deploy_to_aws`                 | `false` stops before deploy, `true` deploys, `null` asks.   |
| `run_federation_workflow`       | Runs federation after manager deploy.                       |
| `fed_sysml_terraform_action`    | `none`, `plan`, `apply`, or `destroy`.                      |
| `auto_run`                      | Runs detected exports without confirmation.                 |
| `remove_infrastructure_on_exit` | Removes EA and SysML kernel containers on exit.             |
| `watch.directory`               | Directory watched for EA exports.                           |

Docker Compose reads `.env` automatically. Use it for AWS credentials, code
mount overrides, ports, and local service settings.

## Git Policy

Commit source models, source code, reusable templates, tests, documentation,
and service provisioning. Do not commit:

- `.env`, credentials, private keys, or local broker configuration;
- EA exports;
- converter input staging or output;
- manager input/output/deployment snapshots;
- federation strategy staging or generated output;
- Terraform state, plans, providers, or locks generated inside output;
- generated Lambda ZIP archives;
- Python environments, caches, or IDE state.

If a generated file is needed for debugging, keep it local or attach it to an
issue/artifact store instead of force-adding it to the repository.

## Tools used in the pipeline

- [Enterprise Architect](https://github.com/EugenBodanov/enterprise-architect)
- [XML to JSON Adapter](https://github.com/EugenBodanov/SysML2CMAdapter)
- [SYSML to JSON Adapter](https://github.com/EugenBodanov/DigitalTwinProfileSysMLv2)
- [AWS Deployer](https://github.com/EugenBodanov/digital-twin-manager)
- [Digital Twin Federation Tool](https://github.com/EugenBodanov/FedSysML)
- [Digital Twin Data Simulator](https://github.com/EugenBodanov/CloudDeployerTestSimulator)
