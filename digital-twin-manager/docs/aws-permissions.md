# AWS permissions

Two kinds of permissions are involved:

- **The deployment principal** is the IAM user whose access key the deployer reads from `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_REGION`. It creates, checks and removes the resources of a twin. The ready-made policy is [`reproduce/aws/deployer-policy.json`](../../reproduce/aws/deployer-policy.json), and the [AWS guide](../../reproduce/aws/README.md) explains how to create the key.
- **The runtime roles** are created by the deployer for the Lambda functions, the state machine, TwinMaker and Grafana. Each gets a policy scoped to the resources of its own twin. They carry the security claims of the paper and are described [below](#runtime-roles).

The reproduction offers two policies for this principal, both for a separate sandbox account. [`sandbox-policy.json`](../../reproduce/aws/sandbox-policy.json) allows whole services (for example `iam:*` and `s3:*`), which is the simplest to set up. [`deployer-policy.json`](../../reproduce/aws/deployer-policy.json) lists only the 104 actions that the code calls. Both apply to all resources (`Resource: "*"`), so neither limits the deployer to one twin. A policy that restricts the resources to the name prefix of a twin is not provided (but could be if necessary).

## The deployment principal

| Service | Used for | Actions |
| --- | --- | --- |
| STS | Resolving the account id for ARNs | `GetCallerIdentity` |
| IAM | Creating, updating and removing the runtime roles and their policies | role and role-policy management, `PassRole` limited to Lambda, Step Functions, TwinMaker and Grafana |
| Lambda | The core functions, one processor per device, the action functions, and the invoke permissions | function and permission management |
| AWS IoT | Things, certificates, the shared IoT policy, the dispatcher rule, and the init-value publish | thing, certificate, policy, rule management, `Publish` |
| EventBridge | The schedules of the two storage movers | rule and target management |
| DynamoDB | The hot table, its point-in-time recovery, and a backup before deletion | table and backup management |
| S3 | The TwinMaker, cold and archive buckets, which `destroy` empties first, including versions | bucket, policy, versioning, encryption and object-version management |
| IoT TwinMaker | The workspace, component types and entities. `destroy` also deletes scenes from the workspace before it deletes the workspace | workspace, component type, entity and scene management |
| Step Functions | The `lambda-chain` state machine | create, describe, delete |
| Grafana | The optional workspace, see below | workspace management, `TagResource` |

The complete action list is in [`deployer-policy.json`](../../reproduce/aws/deployer-policy.json).

Grafana is deployed only if `DEPLOY_MANAGED_GRAFANA` is `true`. The workspace uses AWS SSO authentication, so the account needs IAM Identity Center. AWS then also requires the service-linked role, `sso` actions for the managed application, `organizations:DescribeOrganization` and a few EC2 describe actions, which are part of the policy.

## Runtime roles

Every runtime role has `AWSLambdaBasicExecutionRole` for CloudWatch Logs. The Dispatcher, LambdaChain and per-device Processor roles also have `AWSLambdaRole`, because they invoke a function whose name is not known when the role is created. No role has an AWS-managed `*FullAccess`, `*ReadOnlyAccess` or `*DataAccess` policy. All other permissions are inline policies, built with the ARN builders in `src/deployers/aws/core/aws_arns.py`:

| Role | Grants | Scoped to |
| --- | --- | --- |
| Persister | `dynamodb:PutItem`; `lambda:InvokeFunction` | the hot table of the twin; the Event Checker |
| Event Checker | `iottwinmaker:GetPropertyValueHistory`, `GetPropertyValue`; `lambda:GetFunction`, `InvokeFunction`; `states:StartExecution` | the workspace of the twin; the `<twin>-*` functions; the `lambda-chain` state machine |
| TwinMaker service role | `s3:GetObject`, `PutObject`, `DeleteObject`, `ListBucket`, `GetBucketLocation`; `lambda:InvokeFunction` | the TwinMaker bucket of the twin; the Hot Reader |
| Hot Reader | `dynamodb:Query`; `iottwinmaker:GetEntity`, `GetComponentType` | the hot table; the workspace with its entities and component types |
| Hot-to-Cold Mover | `dynamodb:Query`, `BatchWriteItem`; `s3:PutObject` | the hot table; the cold bucket |
| Cold-to-Archive Mover | `s3:ListBucket`, `ListBucketVersions`, `GetObject`, `GetObjectVersion`, `DeleteObject`, `DeleteObjectVersion` on the source; `s3:GetBucketVersioning` on both; `s3:PutObject` on the target | the cold bucket; the archive bucket |
| Event Feedback | `iot:Publish` | the MQTT feedback topics of the twin's conditions |
| Grafana execution role | `s3:GetObject`; `iottwinmaker:Get*`, `List*`; `iottwinmaker:ListWorkspaces` | the TwinMaker bucket; the workspace; `*` for `ListWorkspaces` |

One statement is broader than the twin: `iottwinmaker:ListWorkspaces` on `*` for Grafana. It is a list action that cannot be scoped to one workspace, and AWS documents it as a requirement of the Grafana plugin ([dashboard IAM role](https://docs.aws.amazon.com/iot-twinmaker/latest/guide/dashboard-IAM-role.html)).

The Cold-to-Archive Mover needs the version permissions to copy objects and delete old source versions, including versions that a delete marker hides. It requires versioning on the archive bucket before it copies and checks the returned version id before it deletes the source.

### Shared IoT policy

All devices of a twin share one IoT policy, `<twin>-iot-policy`, which `policy_document()` in `src/deployers/aws/iot/policy_document.py` builds. Each device keeps its own Thing, certificate and key. The policy uses the variable `${iot:Connection.Thing.ThingName}`, so it is the same for every device:

| Action | Resource | Purpose |
| --- | --- | --- |
| `iot:Connect` | `client/${iot:Connection.Thing.ThingName}` | A device connects with its Thing name as client id |
| `iot:Publish` | `<twin>/iot-data` | Telemetry |
| `iot:Subscribe`, `iot:Receive` | the feedback topics of the conditions | Commands, only if MQTT feedback is configured |

Every statement requires that the certificate is attached to a Thing (`iot:Connection.Thing.IsAttached`) and that the Thing name matches `<twin>-*`. Feedback topics are literal topics without wildcards, and the document stays below the IoT limit of 2,048 characters.

### Other protections

- **Trust policies.** `service_trust_policy()` in `src/deployers/aws/core/trust_policy.py` adds `aws:SourceAccount` to the trust policy of every runtime role, so a service can assume it only for resources of this account (protection against the confused deputy). `aws:SourceArn` is not set, because the resources that assume the roles do not exist yet when the role is created. The invoke permission of the Hot Reader for TwinMaker carries the same condition.
- **Buckets.** The TwinMaker, cold and archive buckets block public access, use versioning and SSE-S3 encryption. The TwinMaker bucket also denies requests without TLS (`aws:SecureTransport`), except for AWS service principals.
- **Tables.** The hot table has point-in-time recovery.

The [security audit](security-audit.md) checks these properties on a deployed twin.
