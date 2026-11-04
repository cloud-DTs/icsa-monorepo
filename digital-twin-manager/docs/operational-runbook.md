# Operational Runbook

The `digital-twin-manager` is an interactive deployment tool. It uses local configuration files to provision AWS resources via Boto3, and all runtime operations are handled natively by AWS services. Because the tool **does not use a state file** (like Terraform), AWS itself is the source of truth, and resource names are the primary tracking mechanism.

## Core CLI Commands

- **`deploy`:** Provisions all infrastructure in a strict dependency order (Core → IoT → Hierarchy → Events → Init Values).
- **`destroy`:** Tears down the infrastructure in reverse order.
- **`info`:** Scans AWS to verify which expected resources currently exist.

## Pre-Deployment Checklist

Before running `deploy`, ensure these files are correctly configured:

1.  **`config.json`:** Verify `digital_twin_name` follows strict regex rules (`[A-Za-z0-9_-]+`, max 10 chars).
2.  **`config_iot_devices.json`:** Define devices, properties, and optional `initValue` fields.
3.  **`config_hierarchy.json`:** Map the devices to TwinMaker Entities and Components.
4.  **`config_events.json`:** Define event rules and actions (ensuring spaces around operators like `<` or `>`).
5.  **`config_credentials.json`:** Ensure valid AWS keys and region are set (**NEVER commit this file**).

## Event Registry / FunctionRegistry Operations

After `deploy` or `apply`, the manager generates `<digitalTwinName>_federation_input.json`. It contains the SSM registry prefix and the strategies that an external federation component can connect.

The manager only reads registry entries at `/<digitalTwinName>/event-registry/{eventName}`; it does not deploy a registration endpoint. For operational checks:

- Confirm that the generated federation input contains the expected `ssm_registry_prefix` and strategies.
- Verify that the external federation component wrote JSON values with a `targets` array.
- Verify that every target `address` is a Step Function ARN accessible to the Event-checker execution role.
- If an entry is absent or invalid, the Event-checker falls back to the local action configured in `config_events.json`.

## Recommended Workflow

Because the tool currently creates not updates, the safest workflow for configuration changes is:

1.  Run `info` to check current state.
2.  Run `destroy` to clear old infrastructure.
3.  Update JSON configs.
4.  Run `deploy` to provision the new setup.
5.  Run a **Runtime Smoke Test** by publishing an MQTT message to `<digitalTwinName>/iot-data` and verifying the data appears in the DynamoDB hot table.

## Key Troubleshooting & Limitations

- **Resource Already Exists:** Since there is no update engine, if a deploy fails halfway or a resource name collides, you must run `destroy` or manually delete the conflicting AWS resource before redeploying.
- **Renaming Dangers:** Never change `digital_twin_name` or `iotDeviceId` between deployments without destroying first, otherwise, the tool will lose track of the old resources.
- **S3 Deletion:** During manual cleanup, remember that S3 buckets must be emptied before they can be deleted.
- **Missing Federation Route:** Check the SSM path and entry format. A missing route intentionally falls back to the local action.
