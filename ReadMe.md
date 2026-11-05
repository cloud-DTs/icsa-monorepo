# TWINFRA: artifact guide

This monorepo implements **TWINFRA: Architectural Decomposition and Automated Deployment of Digital Twins in Cloud**. It connects an annotated system model
to the software architecture and AWS resources of a digital twin. The code retains the names `cloud-dtc` and `digital-twin-manager`.

## From paper concepts to code

**C1: role-based twin decomposition** (Section III, Figure 2). Engineers assign roles to model elements. The [SysML v1 adapter](sysml-v1-adapter/README.md) reads an Enterprise Architect XMI export. The [SysML v2 adapter](sysml-v2-adapter/README.md) reads textual models. Both produce the same four JSON configuration files.

| Paper role       | Configuration produced by the adapters                       | AWS realization in the deployment engine                                                                                                      |
| ---------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Twin             | `config.json`: digital twin name and storage retention       | [Core resources](digital-twin-manager/src/deployers/aws/core/): workspace, message intake, storage, rule evaluation and feedback              |
| Entity           | `config_hierarchy.json`: nested assets                       | [Hierarchy deployer](digital-twin-manager/src/deployers/aws/hierarchy/): TwinMaker entities and containment                                   |
| Component        | `config_iot_devices.json` and hierarchy device bindings      | [Device deployers](digital-twin-manager/src/deployers/aws/iot/): IoT Things, certificates, processing functions and TwinMaker Component Types |
| MeasureAttribute | Device properties and their data types                       | Processing, storage and TwinMaker property reads                                                                                              |
| ConstAttribute   | Properties with `initValue` on generated constant components | [Initial-value deployer](digital-twin-manager/src/deployers/aws/init_values/): initial twin state                                             |
| Condition        | `config_events.json`: comparison and operands                | Event Checker evaluates the latest values                                                                                                     |
| StrategyAction   | `config_events.json`: code, inputs and feedback target       | [Action deployers](digital-twin-manager/src/deployers/aws/event_actions/): Lambda execution; Event Feedback delivers the result               |

The v1 profile uses legacy names: `Component` means the paper's Entity,
`Device` means Component, and `Strategy` means StrategyAction. Its `triggers`
connector encodes a Condition. The v2 models use the paper's role names directly.
The v2 exporter can reuse a TwinMaker Component Type across usages with the
same definition and measurement schema. Each usage keeps its own device ID.

**C2: role-based twin allocation** (Section IV, Figure 3). The
[Python/Boto3 deployment engine](digital-twin-manager/src/deployers/aws/all.py)
reads these files and provisions the resources. Its
[core layers](digital-twin-manager/src/deployers/aws/core/all.py) encode the
provisioning order. The [dependency graph](digital-twin-manager/src/dependency_graph/)
represents resource dependencies for deployment plans.

Figure 3 in the paper applies to the SysML v2 realization.

For a concrete trace, open [MGridICSA.sysml](cloud-dtc-docker/pipeline/digital-twin-profile-sysml-v2/input/MGridICSA.sysml).
`MicroGrid.charger1.p13.power` is a measured value. `charger1Changed` compares it
with a threshold. The [Event Checker](digital-twin-manager/lambda_functions/core/event-checker/lambda_function.py)
reads the values and supplies them to `balance1`. The action's feedback targets
`MicroGrid.battery.controller`. The
[v2 exporter](sysml-v2-adapter/exporter/src/main/java/org/example/TwinExporter.java)
turns these references into device, hierarchy and event configuration. The
deployment engine supplies the ingestion and feedback resources around the
[action code](cloud-dtc-docker/demo-code/microgrid/energy-management/lambda_function.py).

## Case studies and evidence

| Paper material                              | Artifact to inspect                                                                                                                                                                                                   |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CS1: charging point station                 | [MGridICSA.sysml](cloud-dtc-docker/pipeline/digital-twin-profile-sysml-v2/input/MGridICSA.sysml)                                                                                                                      |
| CS2: virtual power plant                    | [VPPMicrogrid.sysml](cloud-dtc-docker/pipeline/digital-twin-profile-sysml-v2/input/VPPMicrogrid.sysml), with 100 households; [generator and scale settings](cloud-dtc-docker/docs/vpp-microgrid.md) |
| Reaction path, Section V-C / Figure 4       | [CS1 MQTT results](evaluator-artifacts/MGridICSA-mqtt-roundtrip.zip), [CS2 MQTT results](evaluator-artifacts/VPP-mqtt-roundtrip.zip)                                                                            |
| Visualization path, Section V-C / Figure 4  | [CS1 TwinMaker results](evaluator-artifacts/MGridICSA-mqtt-twinmaker.zip), [CS2 TwinMaker results](evaluator-artifacts/VPP-mqtt-twinmaker.zip)                                                                  |
| Security assessment, Section V-C / Figure 5 | [Stored findings](evaluator-artifacts/MGridICSA-SecurityEval.json), [audit script and instructions](digital-twin-manager/docs/security-audit.md)                                                                      |

Each measurement ZIP contains `measurements.csv` and `summary.json`. The summary
records the experiment parameters, applied-state fingerprint, sample counts,
failures and latency statistics.

The [evaluation service](digital-twin-evaluator/README.md) resolves targets from saved
**applied deployment state**.

The public [SysML v1 example](cloud-dtc-docker/pipeline/enterprise-architect/projects/DemoProject.qea)
supports inspection of the profile. The industrial CS1 v1 model is withheld for
confidentiality, as stated in Section V-A.

## Run a local model conversion

Use Docker with Compose and Linux containers. Configuration is stored in
`cloud-dtc-docker/.env`, next to `docker-compose.yaml`. From the monorepo root,
open the pipeline directory. Copy the template only if `.env` does not exist:

```powershell
cd cloud-dtc-docker
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Set these values in `.env`:

```dotenv
GH_TOKEN=YOUR_GITHUB_TOKEN
DOCKER_DEFAULT_PLATFORM=linux/amd64
PIPELINE_CODE_HOST_DIR=./demo-code
DTP_V2_INPUT_HOST_DIR=./pipeline/digital-twin-profile-sysml-v2/input
```

The token needs access to the SysML v2 library in GitHub Packages. Compose reads
the variables through [`--env-file`](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/#substitute-with---env-file)
and supplies `GH_TOKEN` as the `gh_token` build secret.

## Deploy and measure

Follow the [pipeline setup and command guide](cloud-dtc-docker/README.md).
The orchestrator requires Python 3.13 or later and `uv`. It starts the
[Enterprise Architect container](enterprise-architect/README.md), including for
SysML v2 runs. Supply an authorized MSI at
`enterprise-architect/installer/EnterpriseArchitect.msi` and a valid license.
The path is relative to the monorepo root. For deployment, set AWS credentials
and region in `.env`; see the [AWS permissions](digital-twin-manager/docs/aws-permissions.md).
The Compose services build from the local projects.

Run from `cloud-dtc-docker`:

```powershell
uv sync --locked
uv run python run_pipeline.py
```

In the running orchestrator, convert CS1:

```text
continue sysml-v2 MGridICSA.sysml
```

At `Continue after sysml-v2 with digital-twin-manager [deploy/plan/apply/N]?`,
enter `n` to inspect the staged configuration first. Then deploy and measure:

```text
continue digital-twin-manager MGridICSA
evaluate mqtt MGridICSA
evaluate mqtt-twinmaker MGridICSA
```

For CS2, use `VPPMicrogrid.sysml` and twin name
`VPP`. Results go to `cloud-dtc-docker/pipeline/digital-twin-evaluation/output/`.
The [evaluation guide](cloud-dtc-docker/docs/digital-twin-evaluation.md) describes
offline experiment planning, configuration and reports. After testing, use
`destroy digital-twin-manager MGridICSA` or the corresponding CS2 command to
remove the deployed twin.

## Implementation scope

The two case studies use mock actions:
[CS1 energy management](cloud-dtc-docker/demo-code/microgrid/energy-management/lambda_function.py)
and the [CS2 MQTT probe](cloud-dtc-docker/demo-code/vpp/mqtt-probe/lambda_function.py).
They return input values to exercise the infrastructure. These measurements
do not evaluate industrial control algorithms or physical actuation. AWS is
the implemented cloud realization.

Regression suites cover [input staging and orchestration](cloud-dtc-docker/tests/),
[validation, deployment planning and policies](digital-twin-manager/tests/), and
[measurement and report behavior](digital-twin-evaluator/tests/).

Additional capabilities include [deployment updates](digital-twin-manager/README.md)
through `plan` and `apply`, and [federation](fed-sysml/README.md) through generated
Terraform for already deployed twins. The [device simulator](digital-twin-simulator/README.md)
logs telemetry by default (`SIMULATOR_MOCK_AWS=true`). Its AWS mode publishes
through the IoT Data HTTPS API. The paper's case-study measurements concern
individual twins and use the separate evaluation service.
