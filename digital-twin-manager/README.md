## Usage
- The Digital Twin can be configured through the configuration files.
- The Digital Twin can be deployed with the `deploy` command.
- The Digital Twin can be destroyed with the `destroy` command.
- With the `info` command you can retrieve information about the Digital Twin cloud resources.

IoT devices use one shared policy per twin: `<digitalTwinName>-iot-policy`.
Run a new `plan`, then `apply`, to migrate existing per-device policies. This
preserves Things, certificates, and local key files. Removing one device keeps
the shared policy; a full twin destroy removes it last. Deployer credentials
also need `iot:GetPolicy` and `iot:ListTargetsForPolicy`. See
[IoT device infrastructure](docs/iot-device-infrastructure.md) for migration and
cleanup behavior.

The shared device policy permits MQTT connections as the registered Thing name
(`<digitalTwinName>-<iotDeviceId>`) and telemetry publishing to
`<digitalTwinName>/iot-data`. Feedback subscriptions and receives use only configured
topics. Certificate-based MQTT clients must use the Thing name as their client ID
before applying this policy.
Run a new `plan`, then `apply`, to replace the known old wildcard document through
an IoT policy version. Certificates and key files are preserved. Policy updates
require `iot:CreatePolicyVersion`; see [AWS permissions](docs/aws-permissions.md).
Saved plans without scoped-policy metadata must be regenerated.

Run `plan`, then `apply`, to update an existing deployment. For every manager-owned Lambda (core, device processors and internal Event Actions), `plan` compares a reproducible ZIP hash with AWS `CodeSha256` and checks the function settings. Code or settings changes use `UPDATE` actions that keep the function ARN. The ZIP hash includes generated configuration files. Hot Reader planning also checks its IAM policy and can update that policy without replacing the role.

Before changing any resource, `apply` checks the planned Lambda packages, settings and AWS revisions, including `NO_CHANGE` actions. If they changed after planning, run `plan` again. Updates use `RevisionId`, wait for AWS completion and verify the deployed hash and settings before processing dependent resources. External Event Action Lambdas are not managed. Functions deployed with the previous ZIP packaging can require one initial code update. Saved plans without the new Lambda metadata must be regenerated.

MQTT Event Feedback planning compares the role's `EventFeedbackScopedAccess` policy in AWS with the configured topics. Topic changes update that policy without replacing the role. Adding the first MQTT feedback creates the policy; removing the last one deletes it. Before `apply` changes any resource, it checks the planned topic policy against the current configuration and the saved AWS policy snapshot. Create a new plan if either changed, or if the saved plan lacks Event Feedback policy metadata.

Event Checker planning also compares its `EventCheckerScopedAccess` inline policy
with AWS. It grants `iottwinmaker:GetWorkspace`, `iottwinmaker:GetComponentType`
and `iottwinmaker:GetEntity` alongside `GetPropertyValueHistory` and
`GetPropertyValue` so that condition and action-input reads can use TwinMaker.
Metadata access is limited to the twin's workspace and its component types and
entities. Missing or stale permissions, including policies that already have
`GetWorkspace` but lack metadata reads, produce an
`UPDATE`; `apply` updates the policy while keeping the role and its attachments.
A missing role produces `DEPLOY`. Apply checks the desired policy and the saved
AWS policy snapshot before any resource changes, including `NO_CHANGE` actions.
Run a new `plan` if either changed or if an older plan lacks Event Checker policy
metadata. After a successful policy update, the next plan reports `NO_CHANGE`.

The Hot Reader supports both shared Component Types with an `iotDeviceId` property and legacy per-device types without that property. Legacy reads check the Component Type schema before deriving the device ID from its name. A shared type with a missing device ID produces an error. The role policy update grants `iottwinmaker:GetComponentType` for this check. Deployer credentials need `iam:GetRolePolicy`, `lambda:UpdateFunctionCode` and `lambda:UpdateFunctionConfiguration`; see [AWS permissions](docs/aws-permissions.md). No code hash needs to be added to `init-state`.

A hierarchy component can reference a managed type through its full `componentTypeId` alone. When that type maps to exactly one configured IoT device, the hierarchy deployer fills its native `iotDeviceId` value. A type shared by multiple devices requires an explicit `iotDeviceId`; configuration validation rejects an ambiguous reference. Run `plan`, then `apply`, to repair missing or incorrect inferred values on existing components through `UPDATE`. This preserves the entities and their other properties. Apply validates the planned inferred bindings for `DEPLOY` and `UPDATE` before changing resources. Updates also verify the saved AWS values and wait for the updated values before recording completion. Saved hierarchy deployment plans without binding metadata require a new `plan`. Legacy types without the native property and external types retain their existing behavior.

With `iotDeviceId`, a hierarchy component's `componentTypeId` is a logical type name. Without `iotDeviceId`, it is a full AWS type ID. For twin `dt`, logical name `dt-pac-sensor` produces AWS ID `dt-dt-pac-sensor`. The dependency graph keeps `dt-pac-sensor` as the logical name.

A hierarchy component can include `componentTypeName` as an optional, non-empty string. This field stores descriptive metadata from the SysML converter. Component Type resolution uses `iotDeviceId` and `componentTypeId`; at least one of these fields is still required.

Devices sharing a Component Type must have identical property names and data types. Property order and per-device `initValue` values can differ. A common schema check runs during configuration validation and before `plan`, direct `deploy` and `apply`, including direct IoT deployer calls. It checks all desired groups before any AWS resource changes. Apply repeats the check before the destroy phase, including types with `NO_CHANGE` actions, to detect incompatible schemas introduced after planning. Validation and deployment use the same property definition builder.

The Cold-to-Archive Mover lists all source object versions, including versions hidden by old delete markers. It copies expired versions to `DEEP_ARCHIVE`, then permanently deletes each copied source version by its `VersionId`. It copies older versions first and keeps the original object keys. Archive bucket versioning must be `Enabled` to preserve multiple source versions. Legacy unversioned buckets remain supported; moving a noncurrent `null` version requires source bucket versioning to be `Enabled`. Delete markers remain in cold storage to keep retained versions hidden. Run `plan`, then `apply`, to update the Lambda and its scoped IAM policy without replacing the role. Apply checks this policy against the saved AWS snapshot before changing resources. Saved plans without Cold-to-Archive policy metadata require a new `plan`.

## Debug ingestion timing

Set `DEBUG=True` in `.env` to measure the delay from the IoT rule to DynamoDB.
The default in `.env.example` is `DEBUG=False`. Values are case-insensitive.
Start a new manager process after changing `.env`, then run `plan` and `apply`.
This updates the existing IoT rule and the Persister Lambda configuration.
Deployer credentials need `iot:ReplaceTopicRule`; see [AWS permissions](docs/aws-permissions.md).
Saved plans without IoT rule metadata require a new `plan`.
Rule read failures stop planning and apply. An access error is treated as a
missing rule only after a complete `ListTopicRules` check confirms its absence.

Rule planning also checks the Dispatcher Lambda's `iot-invoke` permission.
If that permission is missing, `UPDATE` restores it even when the rule SQL is
unchanged. If rule creation succeeds but adding the permission fails, retry
`apply` or run a new `plan` and `apply`. Recovery reuses a rule that matches the
planned configuration and keeps an existing matching permission. A rule or
permission with different contents requires review before applying changes.

For a planned `DESTROY` and `DEPLOY` replacement with the same IoT rule name,
apply checks the old rule against its saved snapshot before deletion. Creation
then requires an absent rule or a rule matching the planned result after a partial
attempt. Older same-name replacement plans without the snapshot require a new `plan`.

When enabled, the IoT rule uses
`SELECT *, timestamp() AS iot_ingested_at_ms FROM '<digitalTwinName>/iot-data'`.
The Dispatcher and supplied processors preserve this field. Custom processors
must also preserve it. The Persister stores these numeric fields:

- `iot_ingested_at_ms`: the IoT rules engine time, in UTC Unix milliseconds.
- `db_write_started_at_ms`: the Lambda time immediately before `PutItem`.
- `ingestion_to_write_ms`: the difference between these timestamps.

After a successful write, the Persister emits a JSON `telemetry_persisted` log
with `db_write_ack_at_ms` and `ingestion_to_ack_ms`. The second duration includes
the database request and response. The stored write timestamp marks request
start; `PutItem` does not return the exact database commit time. These measurements
use clocks from two services and can include clock differences. Repeated writes
to the same device/time key replace the timing values with the latest attempt.
See [IoT timestamp()](https://docs.aws.amazon.com/iot/latest/developerguide/iot-sql-functions.html#iot-function-timestamp)
and [PutItem](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_PutItem.html).

If the ingestion timestamp is missing or is not an integer, the write still
succeeds, but no ingestion duration is calculated. When debug is disabled,
the rule returns to `SELECT *` and the Persister adds no timing fields or logs.
Disable the mode through `.env`, then restart the manager and run `plan` and `apply`.

## Processor deployment timing

Processor IAM roles have no fixed propagation sleep. Lambda creation starts
immediately. If IAM cannot yet find the role, or Lambda reports that it cannot
assume the role, the manager retries up to 10 attempts with delays of 1, 2, 4,
then 8 seconds. Total retry sleep is at most 55 seconds per function, plus API
request time. A successful attempt proceeds immediately. Other errors are raised
without this retry, including access errors, quota errors, invalid packages, and
transport failures. The planned package is built once and reused for all attempts.
See [IAM eventual consistency](https://docs.aws.amazon.com/IAM/latest/UserGuide/troubleshoot.html#troubleshoot_general_eventual-consistency).

## Conventions
- Every deployer should be implemented in its own file.
- Keep components separated, self-contained, and independent.
  Each deploy entity should only be aware of itself. While this is not always achievable, it should be aimed for whenever possible.
- Every Digital Twin resource name should be prefixed with the Digital Twin name.
  This gives all Digital Twin resources a dedicated namespace and makes them clearly distinguishable from unrelated resources in the AWS account.

## Future Ideas
- Improve the handling of constant values. This is less about the deployer itself and more about establishing a consistent mechanism for managing constants across the Digital Twin.
- Possibly remove processor Lambda functions, or refactor them so the processor does not directly invoke the persister.
- Use pagination in Boto3 calls to handle large result sets.
- Testing system or unit tests.
- Recovery mechanism for failed deployments. For example, store the point of failure and provide a `deploy_continue` option to resume.
- Redeployment strategy. For example, when configuration changes, how should the system destroy the old state and deploy the new state?
- Group IAM role deployments to speed up deployment (reducing propagation delays). But keep in mind that this may introduce coupling and reduce the self-contained design.
