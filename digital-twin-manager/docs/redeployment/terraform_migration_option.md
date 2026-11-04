# Migrate Infrastructure Management to Terraform

## Core Idea

Move infrastructure resources from imperative Python/Boto3 deployment code to Terraform resources.

Lifecycle management becomes:

```bash
terraform plan
terraform apply
terraform destroy
```

The existing Python CLI can either:

1. be partially replaced by Terraform commands, or
2. become a wrapper around Terraform.

## What Terraform Solves

Terraform provides built-in mechanisms for:

```text
state management
diff calculation
plan generation
apply execution
resource dependency graph
create/update/delete/replacement classification
remote state
locking
team workflow
CI/CD integration
```

This means the project does not need to implement its own Boto3-based state, diff, plan, and apply engine.

## What Terraform Does Not Solve Automatically

The project still needs to solve:

```text
how to describe all current AWS resources in Terraform
how to import existing resources into Terraform state
how to package Lambda functions
how to handle custom Digital Twin hierarchy logic
how to verify Terraform provider coverage for TwinMaker resources
how to decide between the aws provider, awscc provider, CloudFormation/CDK, or keeping Boto3 for gaps
how to avoid accidental replacement of stateful resources
how to split Terraform modules
```

Terraform should not be treated as an all-or-nothing rewrite. A migration may keep some custom or runtime-oriented flows in Python/Boto3 while moving standard infrastructure resources to Terraform.

---

# Pros

- Built-in `plan`.
- Built-in `apply`.
- Built-in state management.
- No need to write custom diff logic for every resource.
- No need to write custom reconciliation engine for all AWS resources.
- Clear infrastructure-as-code model.
- Good long-term maintainability for standard AWS infrastructure.
- Mature ecosystem and documentation.
- Good support for team workflows.
- Good CI/CD integration.
- Remote state, bucket versioning, and state locking are standard patterns.
- Reduces long-term risk of building a custom mini-IaC tool inside the project.

# Cons

- This is a migration/rewrite of the infrastructure architecture.
- Existing AWS resources must be mapped to Terraform resource definitions.
- Existing AWS resources may need to be imported into Terraform state.
- Lambda packaging/build logic must be redesigned.
- Current Python/Boto3 deployer structure will become obsolete or only partially useful.
- Custom Digital Twin logic may not map cleanly to Terraform.
- Some resources may require `awscc`, CloudFormation/CDK, a custom provider, or continued Boto3 management instead of the standard Terraform AWS provider.
- Requires HCL and Terraform workflow knowledge.
- Requires deciding where to store Terraform state.
- Requires migration plan to avoid destroying existing infrastructure.
- Requires careful handling of runtime data and local artifacts, such as DynamoDB records, S3 telemetry objects, SSM registry values, and IoT certificate/key files.

---

# Short Implementation Plan

## Phase 1: Resource Inventory

Create a complete list of currently managed resources:

```text
Lambda functions
Lambda permissions
IAM roles and policies
DynamoDB tables
S3 buckets
IoT things
IoT rules
IoT policies, certificates, and local auth files if applicable
TwinMaker workspace, component types, entities, and attached components
TwinMaker scenes as externally-created resources that current destroy logic may delete
Grafana workspace
EventBridge rules
Step Functions state machine
```

Track separately as runtime or implicit resources, not current deployer-managed resources:

```text
SSM event registry parameter values managed by the external federation component
CloudWatch log groups created implicitly by Lambda/AWS services
```

## Phase 2: Ownership Decision

Classify each resource:

```text
Terraform-managed
Boto3-managed
manual/external
runtime data
```

A resource must not be managed by both Terraform and Boto3 update logic at the same time.

## Phase 3: Terraform Module Design

Create modules such as:

```text
modules/core
modules/lambda
modules/iot
modules/twinmaker
modules/event-actions
modules/storage
```

Module boundaries should follow ownership boundaries.

## Phase 4: Lambda Packaging Strategy

Decide how Lambda artifacts are built:

```text
archive_file
Makefile/script before terraform apply
CI build artifact
S3 object artifact
```

The chosen strategy must define how Terraform detects code changes, for example through `source_code_hash` for local archives or S3 object version/hash for uploaded artifacts.

## Phase 5: Import Existing Resources

For each existing resource:

```text
write Terraform resource block
terraform import ...
terraform plan
adjust configuration
repeat until plan is safe
```

This phase is the Terraform equivalent of an `adopt` step. It must be completed before Terraform is allowed to apply changes to existing environments. If a resource cannot be imported or represented safely, keep it under Boto3 or manual ownership.

## Phase 6: Add Remote State

Use a remote state backend, for example:

```text
S3 backend
S3 bucket versioning
S3 native lockfile with use_lockfile = true
```

## Phase 7: Replace or Wrap CLI Commands

Decide whether:

```text
deploy -> terraform apply
destroy -> terraform destroy
info -> terraform output / aws describe
```

or whether the old CLI should remain only for runtime/custom operations.

## Phase 8: Safety Rules

Add safeguards:

```text
prevent_destroy for critical resources
explicit approval for replacement
separate environments/workspaces
CI plan checks
manual approval before apply
ownership checks before removing Boto3 deployer code
```

## Phase 9: Documentation

Document:

```text
how to initialize Terraform
how to import existing resources
how to run plan/apply
where state is stored
which resources are Terraform-owned
which resources remain Boto3-owned
```

---

# Assessment

Terraform is the cleanest long-term infrastructure-as-code approach, but it is also the most expensive migration.

For long-term project development, team usage, CI/CD, and production-like infrastructure management, Terraform will be a good option.
