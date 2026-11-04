# TwinMaker Hierarchy Deployer

The TwinMaker hierarchy deployer is a separate deployment phase that creates the AWS IoT TwinMaker entity tree and attaches components to entities. It is implemented in `src/deployers/aws/hierarchy/twinmaker_hierarchy.py`.

This deployer is not part of Core L1-L5 and is not part of IoT L1/L2/L4. It runs after Core and IoT infrastructure have been created.

## Deployment Position

The `deploy` command runs the hierarchy phase in this order:

1. Core deployers create shared resources, including the TwinMaker workspace in Core L4.
2. IoT deployers create per-device resources, including TwinMaker Component Types in IoT L4.
3. The hierarchy deployer creates Entities and attaches Components from `config_hierarchy.json`.
4. Event action deployers and init values run afterward.

The `destroy` command runs the hierarchy phase in the reverse flow, after event actions and before IoT resources are removed.

## Input Configuration

The hierarchy deployer reads `config_hierarchy.json`.

- Entries with `"type": "entity"` become TwinMaker Entities.
- Entries with `"type": "component"` become Components attached to the current parent Entity.
- Nested entity entries create parent-child relationships in TwinMaker.
- Component entries reference Component Types that must already exist.

## Entity Creation

For each entity entry, the deployer calls TwinMaker `create_entity` with:

- `workspaceId`: the TwinMaker workspace name from `digital_twin_name`.
- `entityId`: the configured `id`.
- `entityName`: the configured `name`, or the `id` if `name` is missing.
- `parentEntityId`: set only when the entity is nested under another entity.

Child entities are deployed recursively.

## Component Attachment

For each component entry, the deployer attaches the component to its parent entity using TwinMaker `update_entity` with `componentUpdates`.

The Component Type is resolved from the component entry:

- With both `iotDeviceId` and `componentTypeId`, the type ID is `<digitalTwinName>-<componentTypeId>`. Here `componentTypeId` is the logical name of a managed type.
- With only `iotDeviceId`, the type ID is `<digitalTwinName>-<iotDeviceId>`.
- With only `componentTypeId`, the value is the full ID of an existing type.

Every explicit `iotDeviceId` must match a device in `config_iot_devices.json`. IoT L4 creates the managed Component Types before the hierarchy phase.

For a component with only `componentTypeId`, the deployer matches the full type ID against the effective IoT device configuration. If exactly one device uses that type, the deployer fills its native `iotDeviceId` property. The device ID comes from the configuration. It can differ from the type name. If multiple devices use the type, the component must specify `iotDeviceId`. Configuration validation rejects an ambiguous reference before AWS resources are changed.

Types absent from the managed device configuration remain external references. Legacy managed types without a native `iotDeviceId` property continue to use the Hot Reader's legacy resolution.

## Device Binding Updates

For an otherwise unchanged hierarchy, `plan` checks the inferred device IDs against the native values in AWS. Missing, empty or incorrect values produce an `UPDATE` action. `apply` uses [TwinMaker UpdateEntity](https://docs.aws.amazon.com/iot-twinmaker/latest/apireference/API_UpdateEntity.html) to change only those `iotDeviceId` values. Entity identities, child entities and other component properties are preserved.

For new or replacement entities, `DEPLOY` actions store the inferred device bindings from the configuration. Before any resource changes, `apply` compares these bindings with the current configuration. This check does not require the entity or its Component Types to exist in AWS. The deploy handler checks the bindings again before creating the entity. Saved `DEPLOY` plans without binding metadata must be regenerated with `plan`.

For `UPDATE`, `apply` verifies both the configured bindings and their saved AWS values before changing resources. Changed bindings or AWS values require a new plan. Each entity update must reach `ACTIVE` with the expected property values before the action is recorded as processed. An AWS error or timeout stops the apply operation.

An incomplete AWS response that omits a required component or `iotDeviceId` property produces an error. The deployer does not treat omitted data as an unset value.

## What This Deployer Does Not Create

The hierarchy deployer does not create:

- TwinMaker workspaces, S3 buckets, or IAM roles. These belong to Core L4.
- TwinMaker Component Types. These belong to IoT L4.
- TwinMaker Scenes.
- DynamoDB or S3 telemetry storage.
- Event action Lambdas or runtime event rules.

## Destroy Behavior

During `destroy`, the deployer deletes the configured root entities from `config_hierarchy.json` with recursive deletion enabled. This removes child entities and attached components inside the TwinMaker workspace.

It does not delete Component Types or the TwinMaker workspace itself. Those are removed later by the IoT and Core destroy phases.

## Info Behavior

During `info`, the deployer verifies:

- Expected Entities exist.
- Nested Entities have the expected parent.
- Expected Components are attached to their parent Entity.
- Attached Components use the expected Component Type ID.
