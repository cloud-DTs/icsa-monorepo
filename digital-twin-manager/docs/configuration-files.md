# Configuration Files Overview

The `digital-twin-manager` uses JSON files to define the desired AWS infrastructure setup. The active configuration files act as the single source of truth for the digital twin model and are read during deployment. `config_providers.json` is currently an unused placeholder.

## Key Configuration Files

- **`config.json`**: Contains global settings, such as `digital_twin_name` (used as a strict prefix for all AWS resources) and retention periods for hot/cold storage (`hot_storage_size_in_days`, `cold_storage_size_in_days`).
- **`config_iot_devices.json`**: Defines IoT devices. It lists device IDs, property names (e.g., `temperature`), data types, and optional `initValue`s used to seed initial states.
- **`config_hierarchy.json`**: Defines the logical model in TwinMaker. It maps the devices from `config_iot_devices.json` into a tree structure by defining Entities (e.g., `room-1`) and attaching Components (e.g., `temperatureSensor`) to them. The deployment behavior is documented in `twinmaker-hierarchy-deployer.md`.
- **`config_events.json`**: Sets up automation rules. It contains conditions (e.g., `room-1.temperatureSensor.temperature > 80`) and specifies actions (triggering internal or external Lambda functions) and optional MQTT feedback loops if the condition is met.
- **`config_providers.json`**: Placeholder declaring that all infrastructure layers use AWS. The current application does not read this file during startup, so changing it has no effect until provider selection is implemented in code.
- **`config_credentials.json`**: Stores local AWS access keys. _Must never be committed to Git due to security risks_.

## Interdependencies

The configuration files must remain consistent:

1.  **Devices → Hierarchy:** Every component in `config_hierarchy.json` must reference a valid `iotDeviceId` established in `config_iot_devices.json`.
2.  **Hierarchy → Events:** Event conditions in `config_events.json` must accurately reference the `entityId.componentName.propertyName` path defined in the hierarchy and device configurations.
