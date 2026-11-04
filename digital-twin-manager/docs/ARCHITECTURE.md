# System Architecture

**Note:** Terraform is not used in this project. The infrastructure is provisioned and managed directly using the AWS API via Boto3.

---

## 🛠️ CLI Commands

The system provides three primary commands for infrastructure management: `deploy`, `destroy`, and `info`.

### `deploy`

This command provisions the infrastructure and initializes the digital twin environment.

**Execution Steps:**

- Reads the configuration files.
- Initializes AWS clients.
- Validates the `digital_twin_name` using `sanity_checker.check()`.
- Creates **Core** resources: L1 through L5.
- Creates **IoT** resources: IoT L1, L2, and L4.
- Runs the separate **AWS IoT TwinMaker hierarchy** phase to create Entities and attach Components from `config_hierarchy.json`.
- Provisions the event action Lambda functions.
- Publishes `initValue` payloads to the dispatcher's MQTT topic.

### `destroy`

This command tears down the infrastructure, removing resources in the exact reverse order of their creation.

**Deletion Flow:**

1. `init_values` → `event_actions` → `hierarchy` → `iot` → `core`

**Internal Deletion Order:**

- **IoT Level:** L4 → L2 → L1
- **Core Level:** L5 → L4 → L3Archive → L3Cold → L3Hot → L2 → L1

### `info`

This command retrieves the current state of the deployed environment.

**Execution Steps:**

- Invokes AWS API methods (`describe`, `list`, `get`).
- Verifies the existence of deployed resources.
- Outputs current statuses and relevant AWS Console links.

---

## ⚡ Runtime Data Flow

The following describes the sequence of events during runtime when a device transmits data:

1. **Data Ingestion:** A physical device publishes an MQTT message to the topic:
   `<digitalTwinName>/iot-data`
2. **Rule Trigger:** An **AWS IoT Rule** triggers the **Dispatcher Lambda**.
3. **Dispatch:** The Dispatcher Lambda identifies the `iotDeviceId` and invokes the corresponding **Processor Lambda**.
4. **Processing:** The Processor Lambda normalizes and processes the incoming payload, then invokes the **Persister Lambda**.
5. **Persistence:** The Persister Lambda writes the processed data into the **DynamoDB Hot Table** and subsequently triggers the **Event-Checker Lambda**.
6. **Condition Evaluation:** The Event-Checker Lambda evaluates the conditions defined in `config_events`.
7. **Action Execution:** If a condition evaluates to `true`, the system performs one of two actions:
   - **Direct Invocation:** Triggers the Action Lambda directly.
   - **Workflow Execution:** Starts an AWS Step Function orchestrating the flow: `Action Lambda` → `Event-Feedback Lambda`.
8. **Feedback Loop:** The Event-Feedback Lambda (if triggered) can publish an MQTT feedback message back to the physical device.

## 📊 Visualization and Data Retrieval (TwinMaker & Grafana)

It is important to note that **AWS IoT TwinMaker** and **Grafana** are decoupled from the real-time IoT message processing loop.

- **AWS IoT TwinMaker:**
  - TwinMaker is **not** a direct step in the data ingestion pipeline.
  - Its primary role is to store the digital twin model, which includes the workspace, entities, components, and component types.
  - Data is retrieved on-demand: when a user or dashboard requests a property value or its history, TwinMaker reads the data via a dedicated **hot-reader Lambda**.
- **Grafana:**
  - The system utilizes an **AWS Managed Grafana** workspace.
  - It is used exclusively for visualization, UI, and dashboards. It does not participate in processing or routing incoming IoT messages.
