# AWS access for the reproduction

The parser and `stage` need no AWS access. The deployer creates and removes the
resources of a twin, and the evaluator publishes MQTT messages to the deployed
twin and reads it back. This folder holds the IAM policies for them.

| Tool | AWS access | Policy |
| --- | --- | --- |
| Parser (`parse`), `stage` | none | none |
| Deployer (`deployer`) | create, update and delete the resources of a twin | [`deployer-policy.json`](deployer-policy.json) |
| Evaluator (`evaluate`) | MQTT publish and subscribe, TwinMaker reads | [`evaluator-policy.json`](evaluator-policy.json) |
| Resource count and security audit (optional) | read-only | the AWS managed policies `ViewOnlyAccess` and `SecurityAudit`, plus [`readonly-extras-policy.json`](readonly-extras-policy.json) |

## Use a separate AWS account

The deployer creates IAM roles and attaches policies to them, so its policy
allows far more than a normal application would need. Run it in a sandbox or test
account, never in an account that holds other workloads. The twin's own runtime
roles are scoped to the twin (see [AWS permissions](../../digital-twin-manager/docs/aws-permissions.md)).
The deployer policy uses `Resource: "*"`, because the names of the resources
depend on the twin name, the device ids and the event configuration.

## Create the access key

One IAM user can carry both policies, because the deployer and the evaluator use
the same variables in `.env`. With the AWS CLI, run in this folder, as an
administrator of the sandbox account:

```bash
aws iam create-user --user-name twinfra-reproduce
aws iam put-user-policy --user-name twinfra-reproduce --policy-name Deployer  --policy-document file://deployer-policy.json
aws iam put-user-policy --user-name twinfra-reproduce --policy-name Evaluator --policy-document file://evaluator-policy.json
aws iam create-access-key --user-name twinfra-reproduce
```

Copy `AccessKeyId` and `SecretAccessKey` into `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` in `reproduce/.env`. The AWS console works as well: create
a user without console access, add the two files as inline policies (JSON tab),
and create an access key for use outside AWS.

The deployer reads the long-lived key and the region from the environment. It
does not use session tokens, so temporary credentials do not work with it.

## Account prerequisites

- **Region.** The measurements used `eu-west-1`. A different region needs AWS IoT
  TwinMaker and Amazon Managed Grafana to be available there.
- **Managed Grafana (CS1).** The CS1 twin deploys an Amazon Managed Grafana
  workspace with the `AWS_SSO` authentication provider, so AWS IAM Identity Center
  must be set up in the account. The statement `GrafanaAndDependencies` in the
  deployer policy covers the Grafana, IAM Identity Center, Organizations and EC2
  calls that the workspace needs. If you do not want Grafana, set
  `DEPLOY_MANAGED_GRAFANA=false` in `.env`. The twin then has 210 resources
  instead of the 213 in the paper, because Grafana accounts for 3 of them.
- **Quotas.** CS2 creates 201 IoT things and certificates, 211 IAM roles and 209
  Lambda functions. Check that the account has room, for example for the default
  limit of 1,000 IAM roles. CS1 creates 29 roles and 26 functions.

## Optional: resource count and security audit

The resource count (`digital-twin-manager/scripts/resource_inventory.py`) and the
security audit (`digital-twin-manager/scripts/security_audit.py`) only read. Use a
separate read-only user for them, so the deployer key is not needed:

```bash
aws iam create-user --user-name twinfra-readonly
aws iam attach-user-policy --user-name twinfra-readonly --policy-arn arn:aws:iam::aws:policy/ViewOnlyAccess
aws iam attach-user-policy --user-name twinfra-readonly --policy-arn arn:aws:iam::aws:policy/SecurityAudit
aws iam put-user-policy --user-name twinfra-readonly --policy-name TwinMakerIotReadOnly --policy-document file://readonly-extras-policy.json
aws iam create-access-key --user-name twinfra-readonly
```

The extra policy adds the TwinMaker reads and `iot:GetTopicRule`, which the two
managed policies do not grant. This is the combination that produced the stored
results.

## What each policy contains

- **Deployer.** 11 statements and 104 actions for IAM, Lambda, AWS IoT, EventBridge,
  DynamoDB, S3, IoT TwinMaker, Managed Grafana and Step Functions, plus the
  dependent permissions of Managed Grafana. Every call that the deployer's code
  makes is covered. The explanation of each statement is in
  [AWS permissions](../../digital-twin-manager/docs/aws-permissions.md).
- **Evaluator.** `iot:DescribeEndpoint` to find the MQTT endpoint, `iot:Connect`
  for the client ids `dt-eval-*`, `iot:Publish` for the telemetry topic of the
  twin, `iot:Subscribe` and `iot:Receive` for the feedback topic (the reaction
  path only), and the TwinMaker reads for the visualization path:
  `GetPropertyValueHistory`, `GetWorkspace`, `GetEntity` and `GetComponentType`.
  The earlier `roundtrip` evaluation, which the paper does not use, also needs
  `lambda:InvokeFunction`.

## Clean up

Remove each twin with `destroy` in the deployer, which also deletes its IAM roles.
Resources that still exist cost money. After the experiments, delete the access
keys and the users:

```bash
aws iam delete-access-key --user-name twinfra-reproduce --access-key-id <KEY_ID>
aws iam delete-user-policy --user-name twinfra-reproduce --policy-name Deployer
aws iam delete-user-policy --user-name twinfra-reproduce --policy-name Evaluator
aws iam delete-user --user-name twinfra-reproduce
```
