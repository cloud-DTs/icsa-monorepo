# Add `plan` + `apply` with Resource-Specific Reconciliation

## Core Idea

Add explicit lifecycle commands instead of hiding update behavior inside `deploy`:

```bash
plan
apply
```

`plan` calculates and prints the change set without modifying AWS.  
`apply` should execute a saved plan file by default, for example `plan --out plan.json` followed by `apply plan.json`. The plan must include a desired-state hash and should be rejected if the config files or generated Lambda artifacts changed after planning. Current Lambda packaging writes `zipped.zip` into the source folder during deployment, so this option must either move build artifacts to a separate build/cache directory or hash the Lambda source tree before packaging. A later `apply --refresh` mode may recalculate the plan, but it should print the recalculated change set and require confirmation before mutating AWS.

All Boto3-based variants require resource-specific reconcilers, for example:

```text
LambdaReconciler
LambdaPermissionReconciler
LambdaFunctionUrlReconciler
IAMRoleReconciler
DynamoDBTableReconciler
S3BucketReconciler
IoTThingReconciler
IoTPolicyCertificateReconciler
IoTRuleReconciler
EventBridgeRuleReconciler
StepFunctionReconciler
TwinMakerWorkspaceReconciler
TwinMakerComponentTypeReconciler
TwinMakerEntityReconciler
GrafanaWorkspaceReconciler
```

The current code grants the Event-checker read-only access to its SSM registry path. Registry values are managed by the external federation component. The application also initializes a CloudWatch Logs client but does not create or manage log groups directly.

The key architectural decision is whether to store previous state.

---

## Variant 2A: `plan` + `apply/update` without stored state

### Description

Compares only:

```text
desired state = current configuration files
actual state  = current AWS state
```

No previous state is persisted.

### Pros

- Clear and safe CLI flow: preview first, mutate second.
- No state backend required.
- Easier to implement than the stateful variant.
- Keeps the current Python/Boto3 architecture.
- Preserves modularity through resource-specific reconcilers.
- Good intermediate step before introducing state.

### Cons

- No durable previous state.
- No last-applied drift detection. It can detect Desired-vs-Actual mismatches, but cannot prove whether the mismatch came from out-of-band drift or from a config change that was never applied.
- Lacks automated rollback.

### Implementation Plan

1. Add `plan` and `apply` commands.
2. Define common change types:

```text
CREATE
UPDATE
NO_CHANGE
DELETE_REQUIRED
REPLACE_REQUIRED
DRIFT_UNKNOWN
ERROR
```

3. Define `Plan` and `Change` data structures.
4. Add `PlanBuilder` that calls all resource-specific reconcilers.
5. Add `ApplyExecutor` that applies changes in a safe order.
6. Block destructive operations by default:

```text
DELETE_REQUIRED
REPLACE_REQUIRED
```

7. Add explicit flags later:

```bash
apply --allow-delete
apply --allow-replacement
apply --target lambda:AATwin-dispatcher
```

8. Start with low-risk mutable resources: Lambda code/configuration, EventBridge schedules/targets, IoT rule payloads, and IAM inline policy documents.
9. Treat Lambda invoke permissions as first-class planned changes, either through dedicated reconcilers or as owned child changes of their Lambda/rule reconcilers.
10. Keep stateful or identity-sensitive resources as no-op or replacement-required until safe update rules are designed: DynamoDB tables, S3 buckets, TwinMaker workspace IDs, IoT Things, IoT certificates/keys, and local IoT auth files.

### Assessment

Good intermediate option. It improves transparency and safety without introducing state complexity, but it does not provide strong drift detection or durable recovery.

---

## Variant 2B: `plan` + `apply/update` with stored state

### Description

Compares three sources:

```text
desired state  = current configuration files
previous state = last applied state saved by the tool
actual state   = current AWS state
```

### Pros

- Explicit separation between planning and mutation.
- Desired-vs-previous diff detection.
- Supports drift detection.
- Basis for recovery after partial failures.

### Cons

- Requires state schema design.
- Requires a state backend decision.
- Requires state schema migrations over time.
- Requires locking for remote/team usage.
- Requires apply journal design for reliable recovery.
- Requires saved previous configs/artifacts, backups, and resource-specific rollback logic.
- Can evolve into a custom Infrastructure-as-Code system.

### State Storage Options

MVP:

```text
local JSON file: .digital-twin-manager-state.json
```

Later:

```text
S3 with versioning
S3 conditional writes or DynamoDB lock table for locking
SSM Parameter Store for small state fragments
```

### Implemented MVP: Last-Applied Config Snapshots

The current deployment flow stores the last successfully deployed desired
configuration as local state after `deploy` finishes successfully.

```text
.digital-twin-manager-state/
  metadata.json
  configs/
    config.json
    config_iot_devices.json
    config_events.json
    config_hierarchy.json
```

Existing files at these paths are overwritten on every successful `deploy`.
The same overwrite behavior is available through the manual `init-state`
initializer command, which can bootstrap state for an already deployed
environment before future reconciliation work is added.

The `plan` command initializes the last-applied state in memory from these
files before planning. It does not overwrite the saved state, because the saved
snapshot is the previous-state baseline for desired-vs-previous comparisons.
If an actual AWS resource differs from this previous-state baseline, `plan`
reports drift and does not calculate an update from that resource because there
is no safe last-applied reference.

`config_credentials.json` is intentionally excluded because it contains local
AWS secrets. `config_providers.json` is excluded because the current application
does not read it during deployment.

### Implementation Plan

1. Add `plan` and `apply/update` commands.
2. Define `ResourceReconciler` with state support.
3. Add `StateRepository`.
4. Define a versioned state schema.
5. Implement local state first.
6. Add an `adopt`/bootstrap flow that records existing project-owned AWS resources into state before the first stateful plan.
7. Add drift detection by comparing Previous State vs Actual AWS State.
8. Add apply journal for partial failure recovery.
9. Store recovery metadata where needed: Lambda artifact hashes, previous desired config snapshots, DynamoDB/S3 backup references, and IoT certificate/key file metadata.
10. Update state only after successful resource operation.
11. Block delete/replacement by default and require explicit flags.
12. Implement resource support gradually: Lambda code/configuration, Lambda permissions, EventBridge, IoT rules, IAM, S3/DynamoDB definitions, TwinMaker workspace/component types/entities/components, and Grafana.
13. Keep runtime data and external/manual resources out of state unless an explicit ownership decision has been made.
14. Keep SSM registry values and CloudWatch log groups out of state by default because current deployers do not manage them directly.

### Assessment

Best long-term Boto3-based design. It is cleaner and safer than the stateless variant, but it is more expensive to implement and maintain. If the project should remain Python/Boto3-based, this is the strongest architecture. If infrastructure management becomes the main focus, Terraform should be considered.
