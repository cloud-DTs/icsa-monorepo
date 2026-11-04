# AWS Permissions

This document describes the IAM permissions required by `digital-twin-manager` when it runs against AWS using the credentials from `config_credentials.json`.

The permission set is derived from:

- Direct Boto3 calls in `src/`.
- The command flow in `src/main.py` for `deploy`, `plan`, `apply`, `info`, and `destroy`.
- AWS dependent permissions required by services such as Lambda, Step Functions, AWS IoT TwinMaker, and Amazon Managed Grafana.

The policy examples use `Resource: "*"` because the application creates resources with names derived from `digital_twin_name`, IoT device IDs, event action configuration, and generated AWS resource ARNs. A production policy should narrow resources where possible.

## Application-Managed Permissions

These permissions are required for resources that the application currently creates, checks, or destroys as part of its normal command flow.

### STS

Used to resolve the AWS account ID while building ARNs for Lambda permissions, Step Functions, and TwinMaker.

```text
sts:GetCallerIdentity
```

### IAM

Used to create and remove runtime IAM roles for Lambda, Step Functions, TwinMaker, and Grafana. The application also attaches AWS managed policies and writes inline policies to those roles.

Hot Reader and Event Feedback planning read the current inline policies with `GetRolePolicy`. Event Feedback uses `PutRolePolicy` to add or update permissions when MQTT topics change. When the last MQTT feedback is removed, it uses `DeleteRolePolicy` to remove only `EventFeedbackScopedAccess`. The role and its attached AWS managed policies remain in place. Event Feedback policy updates run before EventChecker code updates in `core_l2`.

```text
iam:CreateRole
iam:GetRole
iam:GetRolePolicy
iam:UpdateAssumeRolePolicy
iam:PutRolePolicy
iam:DeleteRolePolicy
iam:AttachRolePolicy
iam:DetachRolePolicy
iam:ListAttachedRolePolicies
iam:ListRolePolicies
iam:ListInstanceProfilesForRole
iam:RemoveRoleFromInstanceProfile
iam:DeleteRole
iam:PassRole
```

`iam:PassRole` is not called as a Boto3 IAM operation, but it is required when the application passes role ARNs to Lambda, Step Functions, TwinMaker, and Grafana create operations, and to Lambda configuration updates.

### Lambda

Used for core Lambdas, per-device processor Lambdas, optional internal event action Lambdas, and Lambda invoke permissions.

```text
lambda:CreateFunction
lambda:GetFunction
lambda:UpdateFunctionCode
lambda:UpdateFunctionConfiguration
lambda:GetPolicy
lambda:DeleteFunction
lambda:AddPermission
lambda:RemovePermission
```

Internal event action Lambdas are only created when `config_events.json` contains an action with `"external": false`. The current checked-in configuration uses `"external": true`, but the application code supports internal actions.

Planning reads `CodeSha256`, `RevisionId` and function settings from AWS for all manager-owned core, processor and internal Event Action Lambdas. Hot Reader planning also reads its role policy. Code changes use `UpdateFunctionCode`; settings changes use `UpdateFunctionConfiguration`. Both calls use `RevisionId` to reject concurrent changes. After a configuration update, the code update uses the revision returned by that operation. The `function_updated_v2` waiter uses `GetFunction`; it does not require another read permission.

### AWS IoT

Used for IoT Things, certificates, IoT policies, Thing/principal attachments, IoT rules, and init-value publishing.

```text
iot:CreateThing
iot:DescribeThing
iot:DeleteThing
iot:CreateKeysAndCertificate
iot:UpdateCertificate
iot:DeleteCertificate
iot:CreatePolicy
iot:CreatePolicyVersion
iot:GetPolicy
iot:DeletePolicy
iot:DeletePolicyVersion
iot:ListPolicyVersions
iot:ListTargetsForPolicy
iot:AttachPolicy
iot:DetachPolicy
iot:AttachThingPrincipal
iot:DetachThingPrincipal
iot:ListThingPrincipals
iot:ListAttachedPolicies
iot:CreateTopicRule
iot:GetTopicRule
iot:ReplaceTopicRule
iot:ListTopicRules
iot:DeleteTopicRule
iot:Publish
```

`iot:Publish` is used by the init-values deployer when any configured IoT property has `initValue`. The current `config_iot_devices.json` contains init values, so this permission is part of the active deployment flow.

Dispatcher rule planning uses `GetTopicRule` to compare its SQL and target with AWS.
An `UnauthorizedException` is not enough to conclude that a rule is missing.
The lookup checks all `ListTopicRules` pages to confirm absence. If the rule is
listed, the original read error is raised. If listing fails, that error is
raised. This stops `plan`, direct `deploy` and the `apply` preflight before
resource changes. `info` uses the same lookup. Both `iot:GetTopicRule` and
`iot:ListTopicRules` are required. See
[ListTopicRules](https://docs.aws.amazon.com/iot/latest/apireference/API_ListTopicRules.html).
Changing `DEBUG` uses `ReplaceTopicRule` to update the existing rule. This keeps
its name, SQL version, description and error action. Apply checks the saved rule
configuration and AWS snapshot before changing resources. Generate a new plan
after changing `DEBUG`, or when using a saved plan without rule metadata.
Planning also uses `lambda:GetPolicy` to check the Dispatcher's `iot-invoke`
permission. A missing permission produces `UPDATE`; `lambda:AddPermission`
restores only that grant. Retrying a partial deployment reuses a matching rule
and permission. A conflicting grant is reported without replacing it.
The Persister uses its existing `dynamodb:PutItem` and CloudWatch Logs permissions
for debug timing; its runtime role needs no additional permissions. See
[ReplaceTopicRule](https://docs.aws.amazon.com/iot/latest/apireference/API_ReplaceTopicRule.html).

IoT L1 reads the shared `<digitalTwinName>-iot-policy` with `GetPolicy` before
creation or reuse. Planning reads device principals and attached policies to
detect legacy per-device policies. Migration attaches the shared policy before
detaching the legacy policy. `ListTargetsForPolicy` prevents deletion of a policy
that still has targets. Removing a device preserves the shared policy; the
full twin destroy removes it after the device identities.

### EventBridge

Used for scheduled rules that trigger the hot-to-cold and cold-to-archive mover Lambdas.

```text
events:PutRule
events:DescribeRule
events:DeleteRule
events:PutTargets
events:ListTargetsByRule
events:RemoveTargets
```

### DynamoDB

Used for the hot storage table and for creating a table backup before table deletion.

```text
dynamodb:CreateTable
dynamodb:DescribeTable
dynamodb:DeleteTable
dynamodb:CreateBackup
dynamodb:DescribeBackup
dynamodb:UpdateContinuousBackups
```

`dynamodb:UpdateContinuousBackups` enables Point-in-Time Recovery on the Hot table immediately after it becomes active.

### S3

Used for TwinMaker, cold storage, and archive buckets. The destroy flow empties buckets, including versioned objects and delete markers, before deleting the buckets.

```text
s3:CreateBucket
s3:GetBucketPolicy
s3:PutBucketPolicy
s3:PutBucketCORS
s3:PutBucketPublicAccessBlock
s3:PutBucketVersioning
s3:PutEncryptionConfiguration
s3:GetBucketLocation
s3:ListBucket
s3:ListBucketVersions
s3:DeleteObject
s3:DeleteObjectVersion
s3:DeleteBucket
```

`s3:PutBucketPublicAccessBlock`, `s3:PutBucketVersioning`, and `s3:PutEncryptionConfiguration` are used immediately after `s3:CreateBucket` for all three buckets (TwinMaker, cold, archive) to block public access, enable versioning, and enable SSE-S3 encryption. This closed a gap where those buckets relied entirely on the AWS account's org-level default for public-access protection and had no versioning to protect against accidental overwrite/delete — see the ICSA evaluation (`EVALUATION.md` in the bundle root) for the audit that found it.

The TwinMaker bucket also denies HTTP requests with `aws:SecureTransport=false`. AWS service principals are excluded because service calls can redact transport context. `BoolIfExists` on `aws:PrincipalIsAWSService` keeps anonymous HTTP requests covered when that key is absent. Planning reads the bucket policy with `GetBucketPolicy`; `apply` adds the denial with `PutBucketPolicy` without replacing the bucket or removing existing policy statements. If the policy changes in AWS after planning, run `plan` again. See [AWS transport policy guidance](https://docs.aws.amazon.com/AmazonS3/latest/userguide/amazon-s3-policy-keys.html#example-bucket-policies-TLS-version) and [IAM condition operators](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html#Conditions_IfExists).

### AWS IoT TwinMaker

Used for the TwinMaker workspace, component types, entities, and entity component attachments.

```text
iottwinmaker:CreateWorkspace
iottwinmaker:GetWorkspace
iottwinmaker:DeleteWorkspace
iottwinmaker:CreateComponentType
iottwinmaker:GetComponentType
iottwinmaker:DeleteComponentType
iottwinmaker:ListComponentTypes
iottwinmaker:CreateEntity
iottwinmaker:GetEntity
iottwinmaker:UpdateEntity
iottwinmaker:DeleteEntity
iottwinmaker:ListEntities
```

### Amazon Managed Grafana

Used for the Grafana workspace created by Core L5.

```text
grafana:CreateWorkspace
grafana:DescribeWorkspace
grafana:DeleteWorkspace
grafana:ListWorkspaces
grafana:TagResource
```

`grafana:TagResource` is required because the application passes tags during `create_workspace`.

### Step Functions

Used for the Lambda Chain state machine.

```text
states:CreateStateMachine
states:DescribeStateMachine
states:DeleteStateMachine
```

## Cleanup and Scaffold Permissions

These permissions exist because the current destroy logic attempts to clean resources that may exist in the TwinMaker workspace, even though the current deploy flow does not create them.

```text
iottwinmaker:ListScenes
iottwinmaker:DeleteScene
```

The application does not create TwinMaker scenes. During `destroy`, `TwinmakerWorkspaceDeployer` lists and deletes scenes before deleting the workspace. This is defensive cleanup for externally-created or future scene resources.

## AWS-Dependent Permissions

These permissions are not direct Boto3 calls in the application code. They may be required by AWS while fulfilling the application-managed operations above.

### Managed Grafana Dependencies

Amazon Managed Grafana can require service-linked role, AWS IAM Identity Center, AWS Organizations, and EC2 describe permissions while creating or managing a workspace.

```text
iam:CreateServiceLinkedRole
sso:CreateManagedApplicationInstance
sso:DeleteManagedApplicationInstance
sso:DescribeRegisteredRegions
sso:GetSharedSsoConfiguration
organizations:DescribeOrganization
ec2:DescribeSecurityGroups
ec2:DescribeSubnets
ec2:GetManagedPrefixListEntries
```

These permissions are included because the application creates a Grafana workspace with AWS SSO authentication and customer-managed permissions.

## Full Practical Policy

The following policy is intended for the IAM principal whose access keys are stored in `config_credentials.json`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Identity",
      "Effect": "Allow",
      "Action": ["sts:GetCallerIdentity"],
      "Resource": "*"
    },
    {
      "Sid": "IamManagement",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:GetRole",
        "iam:GetRolePolicy",
        "iam:UpdateAssumeRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:ListAttachedRolePolicies",
        "iam:ListRolePolicies",
        "iam:ListInstanceProfilesForRole",
        "iam:RemoveRoleFromInstanceProfile",
        "iam:DeleteRole",
        "iam:CreateServiceLinkedRole"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PassRolesToManagedServices",
      "Effect": "Allow",
      "Action": ["iam:PassRole"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": [
            "lambda.amazonaws.com",
            "states.amazonaws.com",
            "iottwinmaker.amazonaws.com",
            "grafana.amazonaws.com"
          ]
        }
      }
    },
    {
      "Sid": "Lambda",
      "Effect": "Allow",
      "Action": [
        "lambda:CreateFunction",
        "lambda:GetFunction",
        "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration",
        "lambda:GetPolicy",
        "lambda:DeleteFunction",
        "lambda:AddPermission",
        "lambda:RemovePermission"
      ],
      "Resource": "*"
    },
    {
      "Sid": "IoT",
      "Effect": "Allow",
      "Action": [
        "iot:CreateThing",
        "iot:DescribeThing",
        "iot:DeleteThing",
        "iot:CreateKeysAndCertificate",
        "iot:UpdateCertificate",
        "iot:DeleteCertificate",
        "iot:CreatePolicy",
        "iot:CreatePolicyVersion",
        "iot:GetPolicy",
        "iot:DeletePolicy",
        "iot:DeletePolicyVersion",
        "iot:ListPolicyVersions",
        "iot:ListTargetsForPolicy",
        "iot:AttachPolicy",
        "iot:DetachPolicy",
        "iot:AttachThingPrincipal",
        "iot:DetachThingPrincipal",
        "iot:ListThingPrincipals",
        "iot:ListAttachedPolicies",
        "iot:CreateTopicRule",
        "iot:GetTopicRule",
        "iot:ReplaceTopicRule",
        "iot:ListTopicRules",
        "iot:DeleteTopicRule",
        "iot:Publish"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EventBridge",
      "Effect": "Allow",
      "Action": [
        "events:PutRule",
        "events:DescribeRule",
        "events:DeleteRule",
        "events:PutTargets",
        "events:ListTargetsByRule",
        "events:RemoveTargets"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DynamoDB",
      "Effect": "Allow",
      "Action": [
        "dynamodb:CreateTable",
        "dynamodb:DescribeTable",
        "dynamodb:DeleteTable",
        "dynamodb:CreateBackup",
        "dynamodb:DescribeBackup",
        "dynamodb:UpdateContinuousBackups"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:GetBucketPolicy",
        "s3:PutBucketPolicy",
        "s3:PutBucketCORS",
        "s3:PutBucketPublicAccessBlock",
        "s3:PutBucketVersioning",
        "s3:PutEncryptionConfiguration",
        "s3:GetBucketLocation",
        "s3:ListBucket",
        "s3:ListBucketVersions",
        "s3:DeleteObject",
        "s3:DeleteObjectVersion",
        "s3:DeleteBucket"
      ],
      "Resource": "*"
    },
    {
      "Sid": "IoTTwinMaker",
      "Effect": "Allow",
      "Action": [
        "iottwinmaker:CreateWorkspace",
        "iottwinmaker:GetWorkspace",
        "iottwinmaker:DeleteWorkspace",
        "iottwinmaker:CreateComponentType",
        "iottwinmaker:GetComponentType",
        "iottwinmaker:DeleteComponentType",
        "iottwinmaker:ListComponentTypes",
        "iottwinmaker:CreateEntity",
        "iottwinmaker:GetEntity",
        "iottwinmaker:UpdateEntity",
        "iottwinmaker:DeleteEntity",
        "iottwinmaker:ListEntities",
        "iottwinmaker:ListScenes",
        "iottwinmaker:DeleteScene"
      ],
      "Resource": "*"
    },
    {
      "Sid": "GrafanaAndDependencies",
      "Effect": "Allow",
      "Action": [
        "grafana:CreateWorkspace",
        "grafana:DescribeWorkspace",
        "grafana:DeleteWorkspace",
        "grafana:ListWorkspaces",
        "grafana:TagResource",
        "sso:CreateManagedApplicationInstance",
        "sso:DeleteManagedApplicationInstance",
        "sso:DescribeRegisteredRegions",
        "sso:GetSharedSsoConfiguration",
        "organizations:DescribeOrganization",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:GetManagedPrefixListEntries"
      ],
      "Resource": "*"
    },
    {
      "Sid": "StepFunctions",
      "Effect": "Allow",
      "Action": [
        "states:CreateStateMachine",
        "states:DescribeStateMachine",
        "states:DeleteStateMachine"
      ],
      "Resource": "*"
    }
  ]
}
```

## Runtime Role Policies Created by the Application

The permissions above are for the deployment principal. During deployment, the application creates runtime roles and attaches AWS managed or inline policies to those roles. Those runtime policies are not required directly on the deployment principal, except that the principal needs IAM permissions to create and attach them.

Managed policies attached by the application:

```text
arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
arn:aws:iam::aws:policy/service-role/AWSLambdaRole
```

`AWSLambdaBasicExecutionRole` (CloudWatch Logs) is attached to every runtime role. `AWSLambdaRole` (`lambda:InvokeFunction` on all functions) is attached only to the Dispatcher, LambdaChain, and per-device Processor roles, which invoke a downstream Lambda whose exact name isn't fixed at role-creation time. No runtime role uses an AWS-managed `*FullAccess`/`*ReadOnlyAccess`/`*DataAccess` policy — each role that needs DynamoDB, S3, IoT TwinMaker, Lambda, or Step Functions access gets a scoped inline policy instead (see below). This replaced an earlier version of this document/implementation where several roles held `AmazonDynamoDBFullAccess_v2`, `AWSLambda_ReadOnlyAccess`, `AWSStepFunctionsFullAccess`, `AWSIoTDataAccess`, and `AmazonS3FullAccess` — a source-level audit (see the ICSA evaluation, `EVALUATION.md` in the bundle root) found these granted far more than the corresponding Lambda's own source code ever calls.

### Inline Runtime Policies (Scoped)

Each policy is scoped to only the resources that role's Lambda (or, for TwinMaker/Grafana, AWS service) actually calls, using ARN builders in `src/deployers/aws/core/aws_arns.py`.

| Role | Grants | Scoped to |
|---|---|---|
| Persister | `dynamodb:PutItem`; `lambda:InvokeFunction` | this twin's Hot table; the Event-Checker Lambda |
| Event-Checker | `iottwinmaker:GetPropertyValueHistory`/`GetPropertyValue`; `lambda:GetFunction`/`InvokeFunction`; `states:StartExecution` | this twin's TwinMaker workspace; this twin's own `{digitalTwinName}-*` Lambda functions; this twin's LambdaChain state machine |
| TwinMaker service role | `s3:GetObject`/`PutObject`/`DeleteObject`/`ListBucket`/`GetBucketLocation`; `lambda:InvokeFunction` | this twin's TwinMaker S3 bucket; the Hot Reader Lambda |
| Hot Reader | `dynamodb:Query`; `iottwinmaker:GetEntity`/`GetComponentType` | this twin's Hot table; this twin's TwinMaker workspace and its entities/component types |
| Hot-to-Cold Mover | `dynamodb:Query`/`BatchWriteItem`; `s3:PutObject` | this twin's Hot table; this twin's Cold bucket |
| Cold-to-Archive Mover | `s3:ListBucket`/`ListBucketVersions`/`GetObject`/`GetObjectVersion`/`DeleteObject`/`DeleteObjectVersion` (source); `s3:GetBucketVersioning` (source and target); `s3:PutObject` (target) | this twin's Cold bucket; this twin's Archive bucket |
| Event-Feedback | `iot:Publish` | MQTT feedback topics configured in `config_events.json`; reconciled by `plan` and `apply` |
| Grafana execution role | `s3:GetObject`; `iottwinmaker:Get*`/`List*`; `iottwinmaker:ListWorkspaces` | this twin's TwinMaker S3 bucket; this twin's TwinMaker workspace; `Resource:"*"` (see exception below) |

Two statements are intentionally broader than "this twin's own resources" and are documented exceptions, not leftover over-broad grants:

- **Grafana's `iottwinmaker:ListWorkspaces` on `Resource:"*"`** — this is AWS's own documented requirement for the `grafana-iot-twinmaker-app` plugin (a List-level action that can't be scoped to one workspace; see [AWS's dashboard IAM role guide](https://docs.aws.amazon.com/iot-twinmaker/latest/guide/dashboard-IAM-role.html)), not an oversight. The rest of that role's policy matches AWS's documented "no video permissions" template. Grafana deployment is disabled by default via `deploy_managed_grafana`.
- There is deliberately **no third exception for cross-twin federation.** The repo has a "FunctionRegistry" SSM-registry lookup in Event-Checker (`lookup_registry()` in `lambda_functions/core/event-checker/lambda_function.py`, merged from elsewhere — see git history) that lets one twin invoke another twin's Lambda/Step Function. This scoping fix intentionally removed the `ssm:GetParameter` permission that supported it, since federation is out of scope for the current evaluation. The runtime code still *attempts* the SSM call unconditionally (`SSM_REGISTRY_PREFIX` is always set), but its failure is caught by a broad exception handler and falls back to normal local invocation — so this shows up as a harmless `AccessDenied` line in CloudWatch Logs on every action, not a functional break. If federation is needed again, re-adding a scoped `ssm:GetParameter` statement and a bounded federation-target exception is a follow-up, not part of this fix.

### Shared IoT Policy

`IotPolicyDeployer` in `src/deployers/aws/iot/iot_policy.py` manages one policy named `<digitalTwinName>-iot-policy` for each twin. `IotThingDeployer` attaches this policy to every device certificate. Each device keeps its own Thing, certificate and keys.

Adding devices or changing MQTT feedback topics reuses the existing policy. `plan` and `apply` migrate legacy device policy attachments to the shared policy while preserving certificates and local keys. Removing one device preserves the shared policy; a full twin destroy removes it after the device identities.

The policy document grants `iot:*` on `Resource: "*"`. These permissions apply across the AWS account and allow access to all MQTT client IDs and topics.

### Trust Policies

Every runtime role's trust policy (Lambda, Step Functions, TwinMaker, Grafana) is built by `service_trust_policy()` in `src/deployers/aws/core/trust_policy.py`. It adds an `aws:SourceAccount` condition set to the deploying account, so the service principal can only assume the role on behalf of resources in this account (cross-service confused deputy protection). No `aws:SourceArn` is set, because the resources that assume these roles do not exist yet when the role is created.

The Hot Reader Lambda's resource policy (`AllowTwinmakerInvoke`, created in `hot_reader_lambda_function.py`) restricts invocation by `iottwinmaker.amazonaws.com` with `SourceAccount` set to the deploying account. See [Lambda add_permission](https://docs.aws.amazon.com/sdk-for-python/v1/reference/clients/lambda/operations/add_permission/).

This Lambda permission is added when the function is created, including creation through `apply`. Code and configuration updates do not reconcile an existing function's resource policy. The account conditions on role trust policies also apply only to freshly created roles.

### Reconciliation caveat

Hot Reader, Event Feedback and Cold-to-Archive Mover compare their desired inline policy content with AWS and plan `UPDATE` when it differs. Run `plan`, then `apply`, to reconcile those policies without replacing the roles. Other runtime IAM role planners still compare only role names. Changes to their inline policy content require redeploying the affected roles.

The TwinMaker service role grants `s3:GetBucketLocation` on its workspace bucket ARN. For an existing role, update `TwinMakerExecutionPolicy` in IAM before retrying workspace creation; `plan` and `apply` do not reconcile this role's inline policy.

The Cold-to-Archive Mover needs version permissions to copy and permanently delete old source versions, including versions hidden by delete markers. Archive bucket versioning must be `Enabled` when the source key has native S3 versions. The mover checks this before copying and verifies the returned archive version ID before deleting the source. It also supports legacy unversioned buckets. An enabled source bucket protects its legacy `null` versions from replacement by ordinary writes, so these versions are deleted by ID without a condition. Mutable current `null` versions use ETag conditions. For a noncurrent `null` version in a suspended source, the mover stops before copying that key and requires source versioning to be enabled. ETag conditions compare content, not metadata or write identity. See [deleting object versions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/DeletingObjectVersions.html), [ListObjectVersions](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectVersions.html) and [conditional deletes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-deletes.html).

The same limitation applies to the S3 bucket hardening (public-access-block, versioning, SSE-S3 encryption) and DynamoDB Point-in-Time Recovery described above: the corresponding `plan()` methods (`archive_s3_bucket.py`, `cold_s3_bucket.py`, `twinmaker_s3_bucket.py`, `hot_dynamodb_table.py`) do not compare these configuration values. These settings only apply to a freshly created bucket/table; an already-existing one with the same name needs `destroy`+`deploy` to pick them up. The TwinMaker HTTP denial is reconciled separately through `UPDATE`.

## Notes

- `Version: "2012-10-17"` in the JSON policy is the IAM policy language version, not an application version or policy creation date.
- CloudWatch Logs permissions are attached to runtime Lambda roles through `AWSLambdaBasicExecutionRole`; the deployment principal does not call CloudWatch Logs directly.
- If Grafana is removed from Core L5, the Grafana and AWS SSO dependent permissions can be removed from the deployment principal.
- If TwinMaker scene cleanup is removed from `TwinmakerWorkspaceDeployer.destroy`, `iottwinmaker:ListScenes` and `iottwinmaker:DeleteScene` can be removed.
