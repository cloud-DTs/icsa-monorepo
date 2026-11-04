# Init Values

The `initValue` field is an optional property in `config_iot_devices.json` used to seed the digital twin with initial, default, or constant values (e.g., thresholds) immediately after deployment.

## Core Design Choice

An architectural decision is that **initial values are not written directly to the database**. Instead, they are published into the same MQTT ingestion pipeline used by real physical devices. This ensures that initial values:

- Use the same format as runtime messages.
- Pass through the **Dispatcher**, **Processor**, and **Persister** Lambdas.
- Can trigger the **Event-checker Lambda** immediately.
- Are subject to the same storage retention rules as normal data.

## Workflow: `init_values.py`

The initialization logic is executed by the `init_values.py` script after the main infrastructure is deployed:

1.  **Detection:** It iterates through `config_iot_devices.json` to find properties containing an `initValue`.
2.  **Payload Generation:** For each matching device, it builds a synthetic MQTT payload containing the `iotDeviceId`, a current `time` stamp, and all property names configured for that device. Properties that do not define `initValue` are currently included with a `null` value.
3.  **MQTT Publication:** It publishes the payload to the `<digitalTwinName>/iot-data` topic with **QoS 1** (at-least-once delivery).

## Key Interactions

- **Events:** `initValue` is primarily used to provide reference points for event conditions (e.g., comparing a live sensor reading against a constant threshold initialized via this process).
- **TwinMaker:** While `initValue` provides the data, the TwinMaker property itself must still be defined in the **Component Type** via the standard property configuration.
- **Processors:** Because these values follow the standard pipeline, a **Processor Lambda** must exist for the device ID, otherwise the routing will fail.

## Data vs. Infrastructure

In this system, an `initValue` is treated as **runtime data**, not infrastructure. Consequently:

- The `deploy` command publishes the values.
- The init-values deployer has no cleanup logic of its own.
- A full `destroy` removes the storage resources created by the manager, including the DynamoDB hot table and S3 buckets, so stored init values are removed as part of storage teardown.
- The `info` command **does not** inspect their current state.

| Field             | Purpose                                     | Example                       |
| :---------------- | :------------------------------------------ | :---------------------------- |
| **`iotDeviceId`** | Routes the value to the correct processor.  | `battery-threshold-component` |
| **`initValue`**   | The actual constant or default value.       | `23.0`                        |
| **`time`**        | Converted to `id` for DynamoDB persistence. | `2026-05-01T10:00:00.000Z`    |
