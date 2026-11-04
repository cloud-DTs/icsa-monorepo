# AWS Resource Naming

This project uses a strict, prefix-based system for creating AWS resources because it **does not use** state management tools like Terraform or CloudFormation. The manager finds, links, and deletes resources based solely on their names.

## Core Naming Patterns

- **Base Prefix:** Sourced from the `digital_twin_name` variable in `config.json`.
- **Shared Core Resources:** Structured as `<digitalTwinName>-<resource-purpose>` (e.g., `AATwin-dispatcher`).
- **Device-Specific Resources:** Structured as `<digitalTwinName>-<iotDeviceId>-<resource-purpose>` (e.g., `AATwin-sensor-1-processor`).
- **S3 Buckets:** Always forced to lowercase to comply with AWS requirements (e.g., `aatwin-cold-iot-data`).
- **MQTT Topics:** Use a slash separator: `<digitalTwinName>/iot-data`.

## Validation Rules

The `digital_twin_name` prefix is validated before deployment:

- **Maximum Length:** 10 characters.
- **Allowed Characters:** Only letters, numbers, hyphens, and underscores (`[A-Za-z0-9_-]+`).

## Runtime Dependencies (Names as Code Contracts)

The shared IoT device policy is named `<digitalTwinName>-iot-policy`. All device
certificates in the twin use this policy. Legacy `<digitalTwinName>-<iotDeviceId>`
policy names are retained only for migration and cleanup.

Resource names are not just cosmetic labels; the system's runtime logic strictly depends on them:

- **Routing:** The Dispatcher Lambda dynamically constructs the target processor's name and invokes it using the pattern `<digitalTwinName>-<iotDeviceId>-processor`.
- **Data Reading:** The Hot-reader Lambda determines the `iotDeviceId` by stripping the digital twin prefix from the TwinMaker Component Type ID (`<digitalTwinName>-<iotDeviceId>`).
- **Event Execution:** The Event-checker Lambda triggers reaction functions by their specific name: `<digitalTwinName>-<functionName>`.
