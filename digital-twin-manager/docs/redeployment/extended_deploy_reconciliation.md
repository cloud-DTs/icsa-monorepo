# Extend `deploy` with Resource-Specific Reconciliation

## Core Idea

Transform the `deploy` command from create-only into an idempotent reconciliation process:

- **Missing** -> Create.
- **Exists + Mutable changes** -> Update.
- **Exists + immutable changes** -> Replacement required; fail by default or replace only with explicit confirmation/flag.
- **Unchanged** -> No-op.

To preserve modularity, the system should use isolated, resource-specific reconcilers (e.g., `LambdaReconciler`, `DynamoDBTableReconciler`) instead of a single global reconciler.

Current deployers also create resource attachments that must be reconciled explicitly or as owned child changes, such as Lambda invoke permissions, EventBridge targets, IoT certificates/policies, and TwinMaker components attached to entities.

---

## Variant 1A: Without Stored State

Compares only the **Desired State** (configuration files) directly against the **Actual State** (AWS state).

- **Pros:** Minimal CLI changes, requires no state backend, and allows gradual implementation starting with low-risk resources.
- **Cons:** No last-applied drift detection, lacks automated rollback, and offers no preview step before applying changes.
- **Implementation Focus:**
  - Add a `ResourceReconciler` interface: `read_desired()`, `read_actual()`, `diff()`, `apply()`.
  - Refactor existing deployers into resource-specific reconcilers.
  - Keep the existing `deploy` command, but make it execute the reconciliation flow.
  - Compare Desired State vs Actual AWS State.
  - Report Desired-vs-Actual mismatches, but do not label them as proven drift because no previous applied state exists.
  - Apply only safe mutable updates automatically.
  - Mark immutable changes as `REPLACE_REQUIRED` and fail by default unless an explicit flag allows replacement.
  - Start with low-risk mutable resources such as Lambda code/configuration, EventBridge schedules/targets, IoT rule payloads, and IAM inline policy documents.
  - Include Lambda invoke permissions in the same reconciliation boundary as their owning Lambda/rule resources.
  - Do not treat SSM registry values or CloudWatch log groups as current deployer-managed resources; SSM registry values are managed by the external federation component, and CloudWatch log groups are implicit AWS/Lambda resources in the current code.
  - Treat stateful or identity-sensitive resources, such as DynamoDB tables, S3 buckets, TwinMaker workspace IDs, IoT Things, certificates, and local IoT auth files, as no-op or replacement-required until their safe update rules are explicitly designed.

---

## Variant 1B: With Stored State

Compares three sources: **Desired State** (configs), **Previous State** (saved state), and **Actual State** (AWS).

- **Pros:** Minimal CLI changes, last-applied drift detection, and a foundation for recovery after partial failures (stored state does not provide rollback by itself; rollback still requires saved configs/artifacts, backups, an apply journal, and resource-specific recovery logic).
- **Cons:** Overloads the `deploy` command, state management infrastructure (schema, storage, migrations, locking), and lacks an explicit `plan` preview step.
- **Implementation Focus:**
  - Add a `StateRepository` abstraction for loading and saving the previously applied state.
  - Define a versioned state schema, for example `stateVersion`, `digitalTwinName`, `resources`, and per-resource state fragments.
  - Keep state modular: each reconciler owns only its own state fragment.
  - Add a one-time `adopt`/bootstrap step that scans the current AWS resources named by this project and records them as managed state before first stateful deploy.
  - `ResourceReconciler` interface accepts `previous_state`, `desired_state` and `actual_aws_state`.
  - Compare Desired State vs Previous State vs Actual AWS State.
  - Detect drift when Actual AWS State differs from Previous State.
  - Store stable identifiers for each managed resource, such as logical resource key, AWS physical ID, resource type, and last applied hash/config.
  - Store enough recovery metadata for risky resources, such as Lambda artifact hashes, previous desired config snapshots, DynamoDB/S3 backup references, and IoT certificate/key file metadata.
  - Current Lambda packaging writes `zipped.zip` into the Lambda source folder during deployment, so artifact hashing should either move generated archives to a build/cache directory or hash source files before packaging.
  - Update the stored state only after the corresponding AWS change has been applied successfully.
  - Add basic locking if the state is stored remotely, for example with S3 conditional writes or a DynamoDB lock table, to avoid concurrent `deploy` executions.
  - Define state migration rules because the state schema may change as new resource types are added.
  - Mark immutable changes as `REPLACE_REQUIRED` and fail by default unless an explicit flag allows replacement.
  - Keep external/manual resources out of state unless an explicit ownership decision has been made.
  - Keep SSM registry values and CloudWatch log groups out of stored state unless the project adds explicit deployer ownership for them.

---
