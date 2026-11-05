# TWINFRA: artifact guide

This monorepo implements **TWINFRA: Role-based Decomposition and Allocation of Digital Twins to the Cloud**. It connects an annotated system model
to the software architecture and AWS resources of a digital twin. The folder `digital-twin-manager` holds the deployer.

## From paper concepts to code

**C1: role-based twin decomposition** (Section III, Figure 2). Engineers assign roles to the elements of a SysML model. The [SysML v2 parser](sysml-v2-adapter/README.md) reads textual models, and the [SysML v1 parser](sysml-v1-adapter/README.md) reads an Enterprise Architect XMI export. Both turn the annotated model into configuration files for the deployer. Those files are generated and are only an intermediate step: the model is the input to inspect.

| Paper role       | Annotation in a SysML v2 model                                                       | AWS realization in the deployer                                                                                                               |
| ---------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Twin             | `#Twin def`, with `hotDatabaseRetentionDays` and `coldDatabaseRetentionDays`         | [Core resources](digital-twin-manager/src/deployers/aws/core/): workspace, message intake, storage, rule evaluation and feedback              |
| Entity           | `#Entity def` and `#entity`: nested assets                                           | [Hierarchy deployer](digital-twin-manager/src/deployers/aws/hierarchy/): TwinMaker entities and containment                                   |
| Component        | `#Component def` and `#component`: a connected device                               | [Device deployers](digital-twin-manager/src/deployers/aws/iot/): IoT Things, certificates, processing functions and TwinMaker Component Types |
| MeasureAttribute | `#measureAttribute`: a measured value with its data type                             | Processing, storage and TwinMaker property reads                                                                                              |
| ConstAttribute   | `#constAttribute`: a constant value, optionally with a default                       | [Initial-value deployer](digital-twin-manager/src/deployers/aws/init_values/): initial twin state                                             |
| Condition        | `#condition` with `leftOperand`, `operator` and `rightOperand`                       | Event Checker evaluates the latest values                                                                                                     |
| StrategyAction   | `#strategyAction`: code, `inputParameters` and the feedback target `componentTopic`  | [Action deployers](digital-twin-manager/src/deployers/aws/event_actions/): Lambda execution; Event Feedback delivers the result               |

The v1 profile uses legacy names: `Component` means the paper's Entity,
`Device` means Component, and `Strategy` means StrategyAction. Its `triggers`
connector encodes a Condition. The v2 models use the paper's role names directly.
The v2 parser can reuse a TwinMaker Component Type across usages with the
same definition and measurement schema. Each usage keeps its own device ID.

**C2: role-based twin allocation** (Section IV, Figure 3). The
[Python/Boto3 deployer](digital-twin-manager/src/deployers/aws/all.py)
reads these files and provisions the resources. Its
[core layers](digital-twin-manager/src/deployers/aws/core/all.py) encode the
provisioning order. The [dependency graph](digital-twin-manager/src/dependency_graph/)
represents resource dependencies for deployment plans.

Figure 3 in the paper applies to the SysML v2 realization.

For a concrete trace, open [MGridICSA.sysml](reproduce/models/MGridICSA.sysml).
`MicroGrid.charger1.p13.power` is a measured value. `charger1Changed` compares it
with a threshold. The [Event Checker](digital-twin-manager/lambda_functions/core/event-checker/lambda_function.py)
reads the values and supplies them to `balance1`. The action's feedback targets
`MicroGrid.battery.controller`. The
[v2 parser](sysml-v2-adapter/exporter/src/main/java/org/example/TwinExporter.java)
turns these references into the configuration for the deployer. The
deployer supplies the ingestion and feedback resources around the
[action code](reproduce/code/microgrid/energy-management/lambda_function.py).

## Case studies and evidence

| Paper material                              | Artifact to inspect                                                                                                                                                                                              |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CS1: charging point station                 | [MGridICSA.sysml](reproduce/models/MGridICSA.sysml)                                                                                                                                                              |
| CS2: virtual power plant                    | [VPPMicrogrid.sysml](reproduce/models/VPPMicrogrid.sysml), with 100 households; [generator and scale settings](reproduce/docs/vpp-microgrid.md)                                                                  |
| Reaction path, Section V-C / Figure 4       | [CS1 MQTT results](evaluator-artifacts/MGridICSA-mqtt-roundtrip.zip), [CS2 MQTT results](evaluator-artifacts/VPP-mqtt-roundtrip.zip)                                                                             |
| Visualization path, Section V-C / Figure 4  | [CS1 TwinMaker results](evaluator-artifacts/MGridICSA-mqtt-twinmaker.zip), [CS2 TwinMaker results](evaluator-artifacts/VPP-mqtt-twinmaker.zip)                                                                   |
| Figure 4 plots                              | [e2e_pgf.py](evaluator-artifacts/scripts/e2e_pgf.py) turns the `measurements.csv` files into the box plots                                                                                                       |
| Security assessment, Section V-C / Figure 5 | [Stored findings](evaluator-artifacts/MGridICSA-SecurityEval.json), [audit script and instructions](digital-twin-manager/docs/security-audit.md), [Figure 5 script](evaluator-artifacts/scripts/security_pgf.py) |
| Deployed resources, Section V-C / Figure 6  | [Counts per twin](evaluator-artifacts/resource-inventory/), produced by [resource_inventory.py](digital-twin-manager/scripts/resource_inventory.py)                                                              |

Each measurement ZIP contains `measurements.csv` and `summary.json`. The summary
records the experiment parameters, applied-state fingerprint, sample counts,
failures and latency statistics. `VPP-roundtrip.zip` and `MGridICSA-roundtrip.zip`
are earlier runs of the storage roundtrip evaluation, which the paper does not use.

The measurements were recorded on twins deployed under other names. The virtual
power plant twin appears as `VPP` throughout this artifact, so the fingerprints in
the summaries refer to the original deployment. The AWS account ID in the stored
results is replaced by a placeholder.

The [evaluation service](digital-twin-evaluator/README.md) resolves targets from saved
**applied deployment state**.

The SysML v1 parser is included. The industrial CS1 v1 model is withheld for
confidentiality, as stated in Section V-A.

## Reproduce the case studies

The [`reproduce`](reproduce/README.md) folder runs the three tools in order with
Docker Compose: the SysML v2 parser, the deployer and the evaluator. It needs
Docker and AWS credentials, and no licensed software. Deploying creates real
resources in your AWS account and costs money. The [AWS guide](reproduce/aws/README.md)
has the IAM policies for the tools and the steps to create the access key, and
[AWS permissions](digital-twin-manager/docs/aws-permissions.md) explains every permission.

```bash
cd reproduce
cp .env.example .env     # add your AWS credentials
docker compose build
# convert the model: two steps, whose generated files stay in work/
docker compose run --rm parse /pipeline/output/MGridICSA /pipeline/input/MGridICSA.sysml
docker compose run --rm stage MGridICSA
docker compose run --rm deployer      # type: deploy, then exit
docker compose run --rm evaluate run mqtt --deployment /evaluation/deployment --config /evaluation/configs/MGridICSA.mqtt.json --output /evaluation/results
docker compose run --rm deployer      # type: destroy, then exit
```

The README of that folder lists the commands for the visualization path and for
CS2, which uses `VPPMicrogrid.sysml` and the twin name `VPP`.

## Implementation scope

The two case studies use mock actions:
[CS1 energy management](reproduce/code/microgrid/energy-management/lambda_function.py)
and the [CS2 MQTT probe](reproduce/code/vpp/mqtt-probe/lambda_function.py).
They return input values to exercise the infrastructure. These measurements
do not evaluate industrial control algorithms or physical actuation. AWS is
the implemented cloud realization.

Regression suites cover [the VPP generator and its mock action](reproduce/tests/),
[validation, deployment planning and policies](digital-twin-manager/tests/), and
[measurement and report behavior](digital-twin-evaluator/tests/).

An additional capability is [deployment updates](digital-twin-manager/README.md)
through `plan` and `apply`. The [device simulator](digital-twin-simulator/README.md)
logs telemetry by default (`SIMULATOR_MOCK_AWS=true`). Its AWS mode publishes
through the IoT Data HTTPS API. The paper's case-study measurements concern
individual twins and use the separate evaluation service.
