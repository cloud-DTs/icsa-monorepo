# Storage Retention Flow

The system uses a three-tier storage architecture to balance performance and cost. The Core L3 deployers create these layers, ensuring that data is managed throughout its lifecycle from fresh ingestion to long-term archiving.

## Tiered Storage Architecture

- **Hot Storage (DynamoDB):** The **Persister Lambda** writes all fresh IoT data here first. It is the primary source for TwinMaker, Grafana, and the Event-checker.
- **Cold Storage (S3):** Uses the `STANDARD_IA` (Infrequent Access) storage class for older data. Data is stored as JSON chunks.
- **Archive Storage (S3):** Uses `DEEP_ARCHIVE` for long-term retention at the lowest cost. This data is rarely accessed and requires a separate retrieval process.

## Data Movement (Retention Flow)

Data movement is handled by **scheduled background Lambdas**.

1.  **Ingestion:** New data is always written to the **DynamoDB Hot Table**.
2.  **Hot → Cold:** Once a record's age exceeds `hot_storage_size_in_days` (from `config.json`), the **Hot-to-Cold Mover** writes it to the **Cold S3 Bucket** and deletes it from DynamoDB.
3.  **Cold → Archive:** When a cold S3 object's age exceeds `cold_storage_size_in_days`, the **Cold-to-Archive Mover** copies it to the **Archive S3 Bucket** with the `DEEP_ARCHIVE` class and deletes it from the cold bucket.

## Key Read Path Concepts

- **Hot Reader Lambda:** Acts as the bridge for TwinMaker to fetch externally stored property values from the DynamoDB hot table.
- **Current Limitation:** In the current implementation, only hot storage is part of the automated read path. Cold and Archive data are retained for compliance or manual retrieval but are not automatically queried by TwinMaker or the Event-checker.

## Summary Table

| Tier        | Resource  | Written By            | Storage Class  | Use Case                      |
| :---------- | :-------- | :-------------------- | :------------- | :---------------------------- |
| **Hot**     | DynamoDB  | Persister Lambda      | NoSQL          | Real-time monitoring & events |
| **Cold**    | S3 Bucket | Hot-to-Cold Mover     | `STANDARD_IA`  | Historical analysis (older)   |
| **Archive** | S3 Bucket | Cold-to-Archive Mover | `DEEP_ARCHIVE` | Long-term compliance          |
