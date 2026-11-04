# Runtime Ingestion Flow Summary

The runtime ingestion flow describes the path IoT data takes through AWS services after the initial infrastructure deployment is complete.

## Step-by-Step Data Pipeline

- **1. Message Publication:** A physical or simulated device publishes an MQTT message to the `<digitalTwinName>/iot-data` topic. The payload must contain at least the `iotDeviceId` and `time` fields, with all other fields treated as property values.
- **2. Dispatcher Routing:** An AWS IoT Rule receives this message and invokes the shared Dispatcher Lambda. The Dispatcher acts purely as a router: it reads the `iotDeviceId` to build the target function name and asynchronously invokes the device-specific Processor Lambda.
- **3. Device-Specific Processing:** The Processor Lambda (named `<digitalTwinName>-<iotDeviceId>-processor`) transforms, validates, or normalizes the payload. If no custom code is provided, a default processor is used. After processing, it invokes the Persister Lambda.
- **4. Hot Storage Persistence:** The Persister Lambda renames the `time` field to `id` (to serve as the DynamoDB sort key) and writes the item to the DynamoDB hot table. After saving the data, it asynchronously invokes the Event-checker Lambda.
- **5. Event Evaluation:** The Event-checker Lambda evaluates the automation rules defined in `config_events.json`. It does not query DynamoDB directly; instead, it calls TwinMaker APIs, which in turn use the Hot-reader Lambda to pull the necessary external data from the DynamoDB hot table.
- **6. Actions and Feedback:** If the Event-checker Lambda evaluates a condition to be true, it triggers one of two paths based on the configuration:
  - **Without feedback:** The Event-checker directly invokes the specified Action Lambda.
  - **With feedback:** The Event-checker starts an AWS Step Function. This Step Function orchestrates a sequence: it runs the Action Lambda first, and then triggers an Event-feedback Lambda to publish a response message via MQTT.

## Additional Runtime Concepts

- **Storage Lifecycle:** The real-time ingestion pipeline only writes to hot storage. Moving older data to cold (S3) or archive (S3) storage is handled entirely asynchronously by separate, scheduled EventBridge rules and Lambdas.
- **Initialization Values:** Initial values (`initValue`) seeded by `init_values.py` are sent as synthetic MQTT messages and pass through this exact same ingestion pipeline to ensure data consistency.
