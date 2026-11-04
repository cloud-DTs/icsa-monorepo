# TwinMaker Model

AWS IoT TwinMaker acts as the structural modeling layer for the digital twin. It does not ingest real-time IoT messages directly; instead, it provides a logical abstraction over the raw data stored externally in DynamoDB.

**Example:**

- **DynamoDB (Raw Data):** Stores a continuous, contextless stream of numbers (e.g., it records that `sensor-1` reported `22.5` at `10:00 AM`). DynamoDB has no idea what or where "sensor-1" is.
- **TwinMaker (Context & Model):** Provides the physical or logical context. It knows that the data from sensor-1 belongs to the temperatureSensor component located inside the `room-1` Entity. When a user or a Grafana dashboard requests the "temperature of Room 1", TwinMaker acts as the bridge: it uses the shared `hot-reader Lambda` to dynamically fetch the raw `22.5` value from DynamoDB and presents it within its proper spatial context.

## The Model Hierarchy

The digital twin is built using the following nested structure:

- **Workspace:** The top-level boundary (similar to a namespace) for the digital twin, created by the Core L4 deployer.
- **Entity:** A logical object in your model (e.g., `room-1`, `battery`). Entities can have parent-child relationships to form a physical or logical tree.
- **Component:** A specific aspect or module attached to an Entity (e.g., a `temperatureSensor` inside `room-1`). It does not have a parent ID but lives directly inside the Entity's component map.
- **Component Type:** The reusable template (or "class") for a component, created by the IoT L4 deployer based on `config_iot_devices.json`. It defines the data structure (properties) and how to access that data (functions).

## Properties and Data Retrieval

- **External Storage:** Properties (like `temperature`) are marked as `isTimeSeries: true` and `isStoredExternally: true`. This tells TwinMaker that the actual telemetry values are stored outside of the service.
- **The Hot-Reader Lambda:** To fetch these external values, the Component Type's `dataReader` function stores the ARN (Amazon Resource Name) of the shared **hot-reader Lambda**. When a dashboard or event condition requests a value, TwinMaker invokes this Lambda.
- **Data Resolution:** The hot-reader Lambda strips the digital twin prefix from the Component Type ID to figure out the original `iotDeviceId` (e.g., `AATwin-sensor-1` becomes `sensor-1`), and then queries the DynamoDB hot table for the requested data.

## Configuration & Deployment Dependencies

The TwinMaker model physically maps the configurations defined in JSON files:

- `config_iot_devices.json` dictates **what** data exists (creating Component Types).
- `config_hierarchy.json` dictates **where** that data is placed in the model (creating Entities and attaching Components).

Because of strict references, the deployment must follow a specific order: the Workspace and Hot-reader Lambda must exist before Component Types can be created, and Component Types must exist before they can be attached as Components to Entities.
