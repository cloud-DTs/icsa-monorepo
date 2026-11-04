# AWS Resources and Automation Artifacts by Digital Twin Layer

## Purpose

This report counts the AWS resources, persistent configuration artifacts, and
initial-value publish operations automated by the Digital Twin Manager. The
inventory is based on the implementation in `src/deployers/aws` and uses the
five-layer architecture from `EDT_25__CloudDT_engineering.pdf`:

1. Data Acquisition
2. Data Storage
3. Data Processing
4. Digital Twin Management
5. Visualization

AWS Managed Grafana is excluded because its deployment is currently disabled
in [`core/l5.py`](../src/deployers/aws/core/l5.py).

## Counting Rules

The report counts every explicitly created AWS resource and every separately
configured persistent relationship or policy, including:

- IAM roles;
- AWS-managed policy attachments to IAM roles;
- IAM inline policies;
- Lambda functions and resource-based invoke permissions;
- S3 buckets and S3 CORS configuration;
- DynamoDB tables;
- EventBridge scheduled rules and their Lambda targets;
- IoT Core topic rules;
- Step Functions state machines;
- IoT Things, automatically generated certificates, IoT policies, and their
  attachments;
- IoT TwinMaker workspaces, component types, entities, and components;
- MQTT initial-value publish operations.

An embedded configuration is counted as part of its parent resource when it is
supplied in the same create operation. For example, an IAM trust policy is part
of the corresponding IAM role, and a Step Functions definition is part of its
state machine. AWS-managed policies are not created by the tool; each
attachment of such a policy to a role is counted.

## Variables

The resource count depends on deployment configuration:

| Variable | Meaning |
|---|---|
| `D` | Number of unique effective IoT devices in `config_iot_devices.json`. |
| `A` | Number of internal event actions where `type` is `lambda` and `external` is `false`. |
| `H` | Total number of TwinMaker entity entries in `config_hierarchy.json`, including nested entities. |
| `C` | Total number of TwinMaker component entries in `config_hierarchy.json`. |
| `V` | Number of IoT devices containing at least one property with `initValue`. |

`V` is at most `D`. A device produces one MQTT initial-value message even when
several of its properties contain `initValue`. The payload contains all
properties of that device; properties without `initValue` are sent as `null`.

## Mapping Between the Paper and the Code

The paper defines Layer 2 as Data Storage and Layer 3 as Data Processing. The
code uses the opposite numbering for the corresponding Core deployment groups.
This report follows the semantic layers from the paper:

| Paper layer | Code deployment groups |
|---|---|
| Layer 1 — Data Acquisition | `core_l1`, `iot_l1`, and the `init_values` publish phase |
| Layer 2 — Data Storage | `core_l3_hot`, `core_l3_cold`, `core_l3_archive` |
| Layer 3 — Data Processing | `core_l2`, `iot_l2`, `event_actions` |
| Layer 4 — Digital Twin Management | `core_l4`, `iot_l4`, `hierarchy` |
| Layer 5 — Visualization | `core_l5`, currently disabled |

## Summary by Layer

| Layer | AWS resources and persistent configurations | Initial-value messages | Total |
|---|---:|---:|---:|
| Layer 1 — Data Acquisition | `7 + 4D` | `V` | `7 + 4D + V` |
| Layer 2 — Data Storage | `24` | `0` | `24` |
| Layer 3 — Data Processing | `21 + 4D + 3A` | `0` | `21 + 4D + 3A` |
| Layer 4 — Digital Twin Management | `5 + D + H + C` | `0` | `5 + D + H + C` |
| Layer 5 — Visualization | `0` | `0` | `0` |
| **Total** | **`57 + 9D + 3A + H + C`** | **`V`** | **`57 + 9D + 3A + H + C + V`** |

## Layer 1 — Data Acquisition

Layer 1 contains the shared MQTT dispatcher, per-device IoT identity resources,
and initial-value messages published into the ingestion pipeline.

| Resource or configuration | Count |
|---|---:|
| Dispatcher IAM role | `1` |
| AWS-managed policy attachments to the Dispatcher role | `2` |
| Dispatcher Lambda function | `1` |
| Lambda invoke permission for AWS IoT Core | `1` |
| IoT Core topic rule | `1` |
| IoT Thing | `D` |
| Auto-generated IoT certificate | `D` |
| Shared IoT policy | `1` |
| Certificate-to-Thing attachment | `D` |
| IoT-policy-to-certificate attachment | `D` |
| Publish initial-value message | `V` |
| **Layer 1 total** | **`7 + 4D + V`** |

The Dispatcher resources are deployed by
[`core/l1.py`](../src/deployers/aws/core/l1.py). Per-device Things,
certificates, and attachments are created by
[`iot/iot_thing.py`](../src/deployers/aws/iot/iot_thing.py). The shared policy is
managed by [`iot/iot_policy.py`](../src/deployers/aws/iot/iot_policy.py), including
when the twin has no devices. Initial values are
published with QoS 1 by
[`init_values/init_values.py`](../src/deployers/aws/init_values/init_values.py).

## Layer 2 — Data Storage

Layer 2 contains hot, cold, and archive storage together with the functions and
schedules that maintain the storage lifecycle. The Hot Reader is counted here
because the code deploys it as part of `core_l3_hot` and it reads the externally
stored TwinMaker property values from DynamoDB.

| Resource or configuration | Count |
|---|---:|
| IAM roles | `3` |
| AWS-managed policy attachments | `7` |
| IAM inline policies | `1` |
| Lambda functions | `3` |
| Lambda invoke permissions | `3` |
| DynamoDB hot table | `1` |
| S3 cold bucket | `1` |
| S3 archive bucket | `1` |
| EventBridge scheduled rules | `2` |
| EventBridge Lambda targets | `2` |
| **Layer 2 total** | **`24`** |

The detailed split is:

- Hot-to-Cold Mover: one IAM role, three managed-policy attachments, one
  Lambda function, one scheduled rule, one target, and one invoke permission.
- Cold-to-Archive Mover: one IAM role, two managed-policy attachments, one
  Lambda function, one scheduled rule, one target, and one invoke permission.
- Hot Reader: one IAM role, two managed-policy attachments, one inline policy,
  one Lambda function, and one TwinMaker invoke permission.
- Storage: one DynamoDB table and two S3 buckets.

The resources are orchestrated by
[`core/l3_hot.py`](../src/deployers/aws/core/l3_hot.py),
[`core/l3_cold.py`](../src/deployers/aws/core/l3_cold.py), and
[`core/l3_archive.py`](../src/deployers/aws/core/l3_archive.py).

## Layer 3 — Data Processing

Layer 3 contains shared persistence and event-processing resources, one
device-specific processor for every IoT device, and optional internal event
action functions.

| Resource or configuration | Shared | Per device | Per internal action | Total |
|---|---:|---:|---:|---:|
| IAM roles | `4` | `D` | `A` | `4 + D + A` |
| AWS-managed policy attachments | `12` | `2D` | `A` | `12 + 2D + A` |
| IAM inline policies | `1` | `0` | `0` | `1` |
| Lambda functions | `3` | `D` | `A` | `3 + D + A` |
| Step Functions state machines | `1` | `0` | `0` | `1` |
| **Layer 3 total** | **`21`** | **`4D`** | **`3A`** | **`21 + 4D + 3A`** |

The shared resources are:

- Persister IAM role and Lambda function;
- Event Feedback IAM role and Lambda function;
- Event Checker IAM role, inline policy, and Lambda function;
- Lambda Chain IAM role and Step Functions state machine.

Every effective IoT device adds one Processor IAM role, two policy attachments,
and one Processor Lambda. Every internal event action adds one IAM role, one
policy attachment, and one Lambda function. External actions do not create
resources.

The relevant deployers are
[`core/l2.py`](../src/deployers/aws/core/l2.py),
[`iot/l2.py`](../src/deployers/aws/iot/l2.py), and
[`event_actions/lambda_actions.py`](../src/deployers/aws/event_actions/lambda_actions.py).

## Layer 4 — Digital Twin Management

Layer 4 contains the TwinMaker workspace and its supporting AWS resources,
device component types, and the hierarchy model.

| Resource or configuration | Count |
|---|---:|
| TwinMaker IAM role | `1` |
| IAM inline policy | `1` |
| TwinMaker S3 bucket | `1` |
| S3 CORS configuration | `1` |
| IoT TwinMaker workspace | `1` |
| IoT TwinMaker component types | `D` |
| IoT TwinMaker entities | `H` |
| IoT TwinMaker components | `C` |
| **Layer 4 total** | **`5 + D + H + C`** |

One component type is created for every effective IoT device, whether or not it
is referenced by the hierarchy. Entity and component counts are obtained by
recursively traversing `config_hierarchy.json`. Components that reference an
explicit external `componentTypeId` are still created as component instances,
but the external component type is not created by this tool.

The relevant deployers are
[`core/l4.py`](../src/deployers/aws/core/l4.py),
[`iot/l4.py`](../src/deployers/aws/iot/l4.py), and
[`hierarchy/twinmaker_hierarchy.py`](../src/deployers/aws/hierarchy/twinmaker_hierarchy.py).

## Layer 5 — Visualization

No resources are created. The Grafana IAM role and AWS Managed Grafana
workspace deploy calls are commented out, and plan/apply retains only cleanup
actions for resources from older deployments.

| Resource or configuration | Count |
|---|---:|
| Grafana IAM role | `0` |
| AWS Managed Grafana workspace | `0` |
| **Layer 5 total** | **`0`** |

## Summary by AWS Resource Type

| AWS resource or configuration type | Count |
|---|---:|
| IAM roles | `9 + D + A` |
| AWS-managed policy attachments | `21 + 2D + A` |
| IAM inline policies | `3` |
| Lambda functions | `7 + D + A` |
| Lambda invoke permissions | `4` |
| S3 buckets | `3` |
| S3 CORS configurations | `1` |
| DynamoDB tables | `1` |
| EventBridge scheduled rules | `2` |
| EventBridge targets | `2` |
| IoT Core topic rules | `1` |
| Step Functions state machines | `1` |
| IoT Things | `D` |
| Auto-generated IoT certificates | `D` |
| IoT policies | `1` |
| Certificate-to-Thing attachments | `D` |
| IoT-policy-to-certificate attachments | `D` |
| IoT TwinMaker workspaces | `1` |
| IoT TwinMaker component types | `D` |
| IoT TwinMaker entities | `H` |
| IoT TwinMaker components | `C` |
| Publish initial-value messages | `V` |

## Example Configuration

For the repository's `*.example` configuration files:

- `D = 2` effective IoT devices;
- `A = 1` internal event action;
- `H = 1` TwinMaker entity;
- `C = 2` TwinMaker components;
- `V = 1` device containing one or more `initValue` properties.

| Layer | Infrastructure and configuration | Messages | Total |
|---|---:|---:|---:|
| Layer 1 | `15` | `1` | `16` |
| Layer 2 | `24` | `0` | `24` |
| Layer 3 | `32` | `0` | `32` |
| Layer 4 | `10` | `0` | `10` |
| Layer 5 | `0` | `0` | `0` |
| **Total** | **`81`** | **`1`** | **`82`** |

## Items Outside the Main Total

The following are intentionally reported separately because they are implicit
AWS child objects, local outputs, runtime-created resources, or destroy-time
artifacts rather than explicit persistent setup operations:

- Each Lambda is created with `Publish=True`. Counting the resulting immutable
  Lambda version adds `7 + D + A` AWS objects.
- Creating an IoT policy also creates its default policy version. Counting it
  separately adds `1` AWS object.
- The IoT deployer writes three local authentication files per device
  (`certificate.pem.crt`, `private.pem.key`, and `public.pem.key`), adding `3D`
  local files but no additional AWS resources.
- Destroying or replacing the DynamoDB table creates one on-demand DynamoDB
  backup before deleting the table. That backup is not part of a normal fresh
  deployment and may remain after destruction.

If Lambda versions and IoT policy versions are also counted as AWS objects, the  object count for a fresh deployment is:

`65 + 10D + 4A + H + C`

Including initial-value publish operations gives:

`65 + 10D + 4A + H + C + V`
