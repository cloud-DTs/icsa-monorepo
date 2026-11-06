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

When `deploy` is repeated, IoT L1 reads the current Thing
principals before creating a certificate. If one principal is attached, it
reuses that certificate and completes the shared-policy attachment. It keeps
the local certificate and key files. If multiple principals are attached,
deployment stops before creating another certificate.

The shared policy uses explicit MQTT actions and scoped resource ARNs, not `iot:*` on `*`.

Certificate-based MQTT clients must connect with the registered Thing name
`<digitalTwinName>-<iotDeviceId>`. The policy checks
`iot:Connection.Thing.IsAttached` and the twin name. Payloads and certificate file
paths use the device ID without the twin prefix. Certificate clients must use
the registered Thing name as their MQTT client ID.

Devices can publish only to `<Twin>/iot-data`. When MQTT feedback is configured,
they can subscribe and receive on their own default feedback topic (the Thing
name), on explicitly configured custom feedback topics, or both. Custom feedback
topics are shared only because the operator explicitly lists them. They must be
literal topics without `*`, `?`, `#`, `+`, policy substitutions or whitespace.
The existing telemetry topic remains shared; this policy does not validate the
`iotDeviceId` field inside a message.

The shared document has constant size as device counts
increase. Too many custom feedback topics can exceed the 2048-character limit;
configuration preflight then stops before deployment. See
[AWS IoT quotas](https://docs.aws.amazon.com/general/latest/gr/iot-core.html),
and [Thing policy variables](https://docs.aws.amazon.com/iot/latest/developerguide/thing-policy-variables.html).

AWS can delay policy deletion for up to five minutes after detachment; see
[DeletePolicy](https://docs.aws.amazon.com/iot/latest/apireference/API_DeletePolicy.html).
If a full destroy reports a conflict, repeat `destroy` after the delay.

### IoT L2: Device-Specific Processing

- Creates a unique Processor Lambda and IAM Role for each configured device.
- The job of the Processor Lambda is the device-specific processing of a message, for example normalizing the payload, converting units or validating values. The shared Dispatcher Lambda only routes messages.
- The deployer uses custom code for the processor if it exists, or automatically falls back to a default generic processor.
- After processing, this Lambda passes the data to the shared Persister Lambda.

### IoT L4: TwinMaker Component Types

- Creates an AWS IoT TwinMaker Component Type for each device.
- Defines the data structure, including property names, data types, flags indicating whether the data is time-series and stored externally.
- Sets up data reader functions that point to the shared hot-reader Lambda. Since TwinMaker stores only the digital twin model and not the actual telemetry data, these functions act as a bridge, allowing TwinMaker to dynamically fetch external property values from DynamoDB whenever a user or dashboard requests them.
- This layer only creates the Component Type (the template); attaching these components to the actual digital twin Entities is handled separately by the hierarchy deployer based on `config_hierarchy.json`.
