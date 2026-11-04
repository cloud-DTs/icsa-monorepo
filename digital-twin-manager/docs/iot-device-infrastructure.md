# IoT Device Infrastructure

The IoT infrastructure creates device resources from `config_iot_devices.json`. All devices in a twin use one shared IoT policy named `<digitalTwinName>-iot-policy`. Each device has its own Thing, certificate, and authentication files.

The deployment is organized into three specific layers, executed in the order of **L1 → L2 → L4** (and destroyed in the strict reverse order of **L4 → L2 → L1**). Notably, there is no IoT L3 layer because storage is handled by the shared Core L3 infrastructure.

---

## Deployment Layers Breakdown

### IoT L1: Device Identity and Connectivity

- Creates the AWS IoT Thing, which represents the device in AWS IoT Core.
- Generates a certificate, public key, and private key to allow the device to authenticate and publish MQTT messages.
- Stores authentication files locally in an `iot_devices_auth/` directory.
- Creates or reuses the shared IoT policy before creating device identities.
- Attaches the shared policy to each device certificate.

`IotPolicyDeployer` manages the shared policy. `IotThingDeployer` manages Things,
certificates, and their attachments. Removing one device preserves the shared
policy. The policy remains when the device list is empty. Destroying the twin
removes it after all device identities. A policy with remaining targets is not
deleted.

When `deploy` or a saved `apply` is repeated, IoT L1 reads the current Thing
principals before creating a certificate. If one principal is attached, it
reuses that certificate and completes the shared-policy attachment. It keeps
the local certificate and key files. If multiple principals are attached,
deployment stops before creating another certificate.

For an existing deployment, run `plan`, then `apply`. IoT L1 uses `UPDATE` to
attach the shared policy before detaching each legacy `<digitalTwinName>-<iotDeviceId>`
policy. This preserves Things, certificates, and local authentication files.
Unused legacy policies and their non-default versions are then removed.
Policies still attached to other targets are retained. Unrelated policies are
not removed during migration. The shared policy uses explicit MQTT actions and
scoped resource ARNs. It no longer grants `iot:*` on `*`.

Certificate-based MQTT clients must connect with the registered Thing name
`<digitalTwinName>-<iotDeviceId>`. The policy checks
`iot:Connection.Thing.IsAttached` and the twin name. Payloads and certificate file
paths use the device ID without the twin prefix. Certificate clients must adopt
the registered Thing name as their MQTT client ID before the policy update.

The built-in simulator reads the twin name from its configured `<Twin>/iot-data`
topic. It connects with `<Twin>-<iotDeviceId>` as its MQTT client ID.

Devices can publish only to `<Twin>/iot-data`. When MQTT feedback is configured,
they can subscribe and receive on their own default feedback topic (the Thing
name), on explicitly configured custom feedback topics, or both. Custom feedback
topics are shared only because the operator explicitly lists them. They must be
literal topics without `*`, `?`, `#`, `+`, policy substitutions or whitespace.
The existing telemetry topic remains shared; this policy does not validate the
`iotDeviceId` field inside a message.

`plan` emits `UPDATE` for the known old permissive document or a change to the
previously applied feedback permissions. It records the desired document, current
AWS document/default version/ARN, and any nondefault version selected for cleanup.
Other conflicting policy documents are rejected. `apply` checks these snapshots
before any group mutation, including `NO_CHANGE` policies. Dependent Thing work
also validates its planned policy and cannot silently recreate or upgrade it.
Missing metadata or changed settings require a new plan. Processed policy actions
are checked against the desired document when a failed dependent action is retried.
If an AWS write completed but its response or local state save failed, retrying
the saved plan accepts the exact desired document without writing another version.

If an apply stops before saving last-applied configs, a new plan also checks the
saved policy action. It can recognize the recorded AWS document or the intended
document. Policy identity and AWS scope must match. Each new plan records the
current AWS snapshot, so repeated planning preserves this ownership evidence.

The update creates a new default policy version without replacing the policy or
its certificate attachments. At the five-version limit it removes only the
nondefault version named in the plan. The active default remains available if
version creation fails. The shared document has constant size as device counts
increase. Too many custom feedback topics can exceed the 2048-character limit;
configuration preflight then stops before deployment. See
[AWS IoT quotas](https://docs.aws.amazon.com/general/latest/gr/iot-core.html),
[policy version updates](https://docs.aws.amazon.com/iot/latest/apireference/API_CreatePolicyVersion.html),
and [Thing policy variables](https://docs.aws.amazon.com/iot/latest/developerguide/thing-policy-variables.html).

After migration, a device has `NO_CHANGE` when all its principals use the shared
policy and none uses its legacy policy. A legacy policy retained for another
target does not trigger another device update. If that policy later has no
targets, `plan` schedules an `UPDATE` to remove it. Planning reads all target
pages needed for this check. AWS errors other than a missing policy stop planning.

Migration needs one free policy slot and permission to call `iot:GetPolicy` and
`iot:ListTargetsForPolicy`, in addition to the existing IoT permissions.
AWS can delay policy deletion for up to five minutes after detachment; see
[DeletePolicy](https://docs.aws.amazon.com/iot/latest/apireference/API_DeletePolicy.html).
If cleanup reports a conflict, run a new `plan` and `apply` after that delay.
Device removal keeps its action pending if policy deletion reports a conflict;
repeat `apply` after the delay.
If a full destroy reports a conflict, repeat `destroy` after the delay.

### IoT L2: Device-Specific Processing

- Creates a unique Processor Lambda and IAM Role for each configured device.
- Unlike the shared Dispatcher Lambda (which only routes messages), the Processor Lambda handles device-specific tasks like normalizing payloads, converting units, and validating values.
- The deployer uses custom code for the processor if it exists, or automatically falls back to a default generic processor.
- After processing, this Lambda passes the data to the shared Persister Lambda.

### IoT L4: TwinMaker Component Types

- Creates an AWS IoT TwinMaker Component Type for each device.
- Defines the data structure, including property names, data types, flags indicating whether the data is time-series and stored externally.
- Sets up data reader functions that point to the shared hot-reader Lambda. Since TwinMaker stores only the digital twin model and not the actual telemetry data, these functions act as a bridge, allowing TwinMaker to dynamically fetch external property values from DynamoDB whenever a user or dashboard requests them.
- This layer only creates the Component Type (the template); attaching these components to the actual digital twin Entities is handled separately by the hierarchy deployer based on `config_hierarchy.json`.
