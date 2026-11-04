# Events and Actions

The event system automates responses to IoT data changes. Rules are defined in `config_events.json`, evaluated by the **Event-checker Lambda**, and executed via **Action Lambdas**.

## Event Object Structure

Each event rule consists of three main parts:

- **Condition:** An expression (e.g., `entityId.component.property > DOUBLE(80.0)`) that determines when an action triggers.
- **Action:** Defines the target Lambda function and whether it is **internal** (deployed by the manager) or **external** (exists independently).
- **Feedback (Optional):** Defines an MQTT message to be sent after the action completes.

## Runtime Logic

The event process is triggered by the **Persister Lambda** immediately after new data is written to the DynamoDB hot table:

1.  **Value Fetching:** The Event-checker does not query DynamoDB directly. It requests property values through **AWS IoT TwinMaker**, which uses the **Hot-reader Lambda** to pull data from hot storage.
2.  **Condition Evaluation:** The Event-checker parses simple comparisons (`<`, `>`, `==`) by splitting strings on spaces.
3.  **Execution Paths:**
    - **Federated Action:** If SSM contains registered targets for the event, the Event-checker starts each target Step Function with the resolved input parameters.
    - **Simple Action:** If the condition is true and no feedback is configured, the Event-checker invokes the **Action Lambda** directly.
    - **Feedback Flow:** If feedback is required, the Event-checker triggers the **Lambda Chain Step Function**. This orchestrates a sequence: **Action Lambda** → **Event-feedback Lambda**.

## Deployment and Management

- **Internal Actions (`external: false`):** The manager creates the necessary IAM Roles and Lambda functions during the `deploy` phase.
- **External Actions (`external: true`):** The manager assumes the Lambda already exists with the name `<digitalTwinName>-<functionName>` and does not create or delete it.
- **Feedback Delivery:** The **Event-feedback Lambda** can publish either a static message or the actual result returned by the Action Lambda to a specified MQTT topic.

## Event Registry / FunctionRegistry

Core L2 reads federation routing entries from AWS Systems Manager Parameter Store at `/<digitalTwinName>/event-registry/{eventName}`.

- **Reader:** The Event-checker has read-only access to the twin's registry path.
- **Writer:** An external federation component owns registry population; the manager does not deploy a registration Lambda or Function URL.
- **Format:** Each SSM value is JSON with a `targets` array. Every target contains an `address` identifying a Step Function state machine ARN.
- **Federation input:** After `deploy` or `apply`, the manager writes `<digitalTwinName>_federation_input.json` with the SSM prefix, available strategies, Hot-reader ARN, and TwinMaker workspace ID.
- **Fallback:** If no registry entry exists, the Event-checker uses the local action/feedback flow from `config_events.json`.

## Key Distinctions

| Lambda Type        | Purpose                                          | Triggered By                    |
| :----------------- | :----------------------------------------------- | :------------------------------ |
| **Processor**      | Normalizes raw device data.                      | Dispatcher Lambda.              |
| **Persister**      | Writes to DynamoDB and starts event checking.    | Processor Lambda.               |
| **Event-checker**  | Evaluates rules in `config_events.json`.         | Persister Lambda.               |
| **Action**         | Performs business logic when conditions are met. | Event-checker or Step Function. |
| **Event-feedback** | Sends MQTT notifications after an action.        | Step Function.                  |
| **Federation target** | Runs a federated strategy registered in SSM. | Event-checker via Step Functions. |
