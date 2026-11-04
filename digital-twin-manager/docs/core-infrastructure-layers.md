# Core Infrastructure Layers

## Core vs. IoT Infrastructure

- **Core infrastructure:** Shared AWS resources used by the entire digital twin (e.g., one Dispatcher, one DynamoDB table, one TwinMaker workspace).
- **IoT infrastructure:** Per-device resources created for each configured IoT device (e.g., AWS IoT Things, device-specific processor Lambdas).

## Deployment Groups (L1–L5)

The layers L1 through L5 represent deployment groups to define creation and destruction order.

- **Deploy order:** Core L1 → Core L2 → Core L3 Hot → Core L3 Cold → Core L3 Archive → Core L4 → Core L5.
- **Destroy order:** Strictly reversed (L5 → L1) to avoid AWS dependency errors (e.g., deleting IAM roles before their Lambdas).

The TwinMaker hierarchy deployer is a separate post-IoT deployment phase, not a Core or IoT layer. It is documented in `twinmaker-hierarchy-deployer.md`.

## Layer Breakdown

### Core L1: Dispatcher Entry Layer

- **Components:** Dispatcher IAM Role, Lambda Function, and IoT Rule.
- **Purpose:** Listens to the shared MQTT topic (`<digitalTwinName>/iot-data`) and routes incoming messages to the correct device-specific processor Lambda. It does not store data or evaluate events.

### Core L2: Processing, Persistence, Events, and Federation Routing

- **Components:** Persister, Event-checker, Event-feedback, related IAM Roles, and the Lambda Chain Step Function.
- **Purpose:**
  - The Persister writes processed data into the hot DynamoDB table.
  - The Event-checker evaluates conditions from `config_events.json`.
  - Step Functions and Feedback Lambdas handle event actions and return MQTT feedback.
  - The Event-checker reads optional federation targets from AWS Systems Manager Parameter Store under `/<digitalTwinName>/event-registry/` and starts the registered Step Functions.
  - After `deploy` or `apply`, the manager exports the twin's federation metadata, including the SSM prefix and available strategies, to `<digitalTwinName>_federation_input.json`.

The manager does not deploy an API for writing registry entries. Registry population is owned by the external federation component.

### Core L3: Storage Lifecycle (Hot, Cold, Archive)

- **L3 Hot:** Uses DynamoDB to store fresh IoT data. Includes a Hot Reader Lambda that AWS IoT TwinMaker uses to fetch externally stored property values.
- **L3 Cold & Archive:** S3 buckets for aged data.
- **Data Movement:** Scheduled EventBridge rules trigger Lambdas to automatically move older records: DynamoDB (Hot) → S3 (Cold) → S3 (Archive) based on retention configurations.

### Core L4: AWS IoT TwinMaker

- **Components:** TwinMaker Workspace, S3 Bucket, and IAM Role.
- **Purpose:** Creates the TwinMaker workspace boundary and its supporting bucket and IAM role. Component Types are created later by the IoT L4 deployer, while Entities and attached Components are created by the separate hierarchy deployer from `config_hierarchy.json`. Scenes are not created by Core L4 during deployment.

### Core L5: Grafana Visualization

- **Components:** AWS Managed Grafana Workspace and IAM Role.
- **Purpose:** Provides the UI and dashboard infrastructure for end-users. It does not process incoming IoT messages.
