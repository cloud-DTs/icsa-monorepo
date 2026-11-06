# From roles to resources

This page details paper Section IV-A (role-based twin allocation, contribution C2). It lists the AWS resources that each architectural element of Fig. 3 consists of, which role requires the element, how often it exists, and where the deployer creates it. [Provisioning order and dependencies](provisioning-order.md) covers Section IV-B, the order in which the deployer creates them.

## Principle

The model states what each element is (its role), not how a platform realizes it. The allocation decides once per role which AWS resources realize it. The scope of an element follows from its role:

- **Per Component:** every Component has its own identity, message handling and representation, for security and separation of concerns.
- **Per StrategyAction:** every StrategyAction has its own function, because its code differs from that of every other.
- **Per Entity:** an Entity has only a representation in the workspace.
- **Per Twin:** storage, message intake, condition evaluation, feedback delivery, the workspace and the visualization exist once, or are defined once and instantiated per invocation.

MeasureAttributes, ConstAttributes and Conditions create no resource. They configure the elements of their Component, Entity or Twin: a MeasureAttribute adds a property to the component type of its Component, a ConstAttribute adds a property with an initial value (published once as a message, see [init values](init-values.md)), and a Condition adds a rule to the configuration of the Event Checker.

Every connection between two elements has a permission, which the deployer derives together with the elements and restricts to the resources of the twin ([AWS permissions](aws-permissions.md)).

## Elements and resources

Abbreviations as in Fig. 3: IAM = roles, role policy attachments and inline policies; L = Lambda functions and their invoke permissions; IoT = AWS IoT Core; T = IoT TwinMaker; S3 = buckets, CORS configurations and bucket policies; E = EventBridge rules and targets; Sf = Step Functions; G = Managed Grafana. Source paths are in [`src/deployers/aws`](../src/deployers/aws).

### Per Component (once per device)

| Element | Resources | Source |
| --- | --- | --- |
| Component Identity | IoT 4: Thing, certificate, attachment of the certificate to the Thing, attachment of the shared policy to the certificate | `iot/iot_thing.py` |
| Component Message Handling | IAM 3: role with `AWSLambdaBasicExecutionRole` and `AWSLambdaRole`; L 1: the processor function | `iot/processor_*.py` |
| Component Representation | T: a component type, shared by all Components with the same type, with one time-series property per MeasureAttribute; T 1: the component in the workspace | `iot/twinmaker_component_type.py`, `hierarchy/` |

### Per Entity and per StrategyAction

| Element | Resources | Source |
| --- | --- | --- |
| Entity Representation | T 1: the entity in the workspace | `hierarchy/twinmaker_hierarchy.py` |
| StrategyAction Execution | IAM 2: role with `AWSLambdaBasicExecutionRole`; L 1: the action function | `event_actions/lambda_actions.py` |

### Per Twin

| Element | Resources | Configuration | Source |
| --- | --- | --- | --- |
| Component Policy | IoT 1 | One policy for all devices; the variable `${iot:Connection.Thing.ThingName}` limits each certificate to its own Thing | `iot/iot_policy.py` |
| Message Intake | IAM 3, L 2, IoT 1: dispatcher role, function and invoke permission, and the IoT rule | The rule selects `<twin>/iot-data`; the dispatcher invokes `<twin>-<device>-processor` | `core/dispatcher_*.py` |
| Storage | IAM 3, L 1, DB 1, S3 2: persister role and function, the hot table, the cold and archive buckets | Hot table keyed by device and message id, on-demand billing, point-in-time recovery; the persister invokes the Event Checker | `core/persister_*.py`, `core/hot_dynamodb_table.py`, `core/cold_s3_bucket.py`, `core/archive_s3_bucket.py` |
| Storage Tier Management | IAM 6, L 4, E 4: two movers with role, function and invoke permission, two schedule rules with one target each | Hot to cold daily at 12:00 UTC after `hotDatabaseRetentionDays`; cold to archive daily at 18:00 UTC after `coldDatabaseRetentionDays` | `core/hot_cold_mover_*.py`, `core/cold_archive_mover_*.py` |
| Condition Evaluation | IAM 3, L 1: Event Checker role and function | One rule per Condition in its configuration; it reads values from the workspace and starts the state machine | `core/event_checker_*.py` |
| Feedback Delivery | IAM 5 (6 with MQTT feedback), L 1, Sf 1: feedback role and function, state machine and its role | The `lambda-chain` runs the action and then the feedback; the feedback role gets an inline policy that allows `iot:Publish` on the configured topics | `core/event_feedback_*.py`, `core/lambda_chain_*.py` |
| Twin Workspace | IAM 5, S3 3, T 1, L 2: TwinMaker role, bucket with CORS and bucket policy, the workspace, Hot Reader role and function with its invoke permission | The Hot Reader implements the data reader of every component type and reads the hot table | `core/twinmaker_*.py`, `core/hot_reader_*.py` |
| Visualization | IAM 2, G 1 | Optional, only if `DEPLOY_MANAGED_GRAFANA` is `true`; the role reads the workspace and its bucket | `core/grafana_*.py` |

## The two paths

A measurement takes one of two paths through these elements.

- **Reaction path:** Message Intake → Component Message Handling → Storage → Condition Evaluation → Feedback Delivery. The dispatcher selects the processor of the device, the processor hands the message to the persister, which stores it and invokes the Event Checker. If a Condition holds, the state machine runs the StrategyAction and then the feedback, which publishes to the topic of the target Component. See [runtime ingestion flow](runtime-ingestion-flow.md) and [events and actions](events-and-actions.md).
- **Visualization path:** Storage → Twin Workspace → Visualization. TwinMaker asks the Hot Reader for the values of a property, and the Hot Reader queries the hot table. Grafana reads through the workspace.

## Counting the resources

The number of resources of a twin follows from the model. With D Components, A StrategyActions, T component types, H Entities, C components in the workspace, F = 1 if a feedback topic is configured and G = 1 if Grafana is deployed:

```
N = 50 + 8D + 3A + T + H + C + F + 3G
```

The constant is the sum of the per-Twin rows without F and G (1 + 6 + 7 + 14 + 4 + 7 + 11 = 50). Each device adds 4 (identity) and 4 (message handling), each StrategyAction 3, and the workspace gets one type per component type, one entity per Entity and one component per Component.

Example, the VPP model with two households (`python reproduce/scripts/generate_vpp_microgrid.py --households 2`): 5 devices (the grid telemetry and a Sensor and a BESS per household), 1 StrategyAction, 3 component types, 4 entities (Grid, CW and the two households), 5 components, MQTT feedback and no Grafana give N = 50 + 40 + 3 + 3 + 4 + 5 + 1 = 106. The deployed twin has exactly 106 resources. CS1 has 213 and CS2 1,968 in the paper.

[`resource_inventory.py`](../../digital-twin-evaluator/scripts/resource_inventory.py) counts the resources that exist in AWS and compares them with this formula.
