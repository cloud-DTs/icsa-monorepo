# AWS access for the reproduction

The `parsers` and `stage` need no AWS access. The deployer creates and removes the
resources of a twin, and the evaluator publishes MQTT messages to the deployed
twin and reads it back. Both use one access key in `reproduce/.env`.

## Quick start

Use a **separate sandbox AWS account**. The deployer creates IAM roles and
attaches policies to them, so it needs wide permissions, and you should not run it
in a production-use account.
Also note that this is a research prototype, and the deployer may create and remove resources in your account.
Use at your own risk.

[`sandbox-policy.json`](sandbox-policy.json) allows whole services: `iam:*`,
`lambda:*`, `s3:*`, `iot:*`, `events:*`, `dynamodb:*`, `states:*`,
`iottwinmaker:*` and `grafana:*`, plus the few calls that Managed Grafana needs
from IAM Identity Center, Organizations and EC2. It covers the deployer and the
evaluator, and it is short enough to be an inline policy of a user. In the sandbox
account, as an administrator:

```bash
cd reproduce/aws
aws iam create-user --user-name twinfra-reproduce
aws iam put-user-policy --user-name twinfra-reproduce --policy-name Twinfra --policy-document file://sandbox-policy.json
aws iam create-access-key --user-name twinfra-reproduce
```

Copy `AccessKeyId` and `SecretAccessKey` into `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` in `reproduce/.env`, and set `AWS_REGION`. In the AWS
console, create a user without console access, add the policy as an inline policy
(JSON tab) and create an access key for use outside AWS.

The deployer reads a long-lived key and the region from the environment. It does
not work with session tokens.

## Account prerequisites

- **Region.** The measurements used `eu-west-1`. Another region needs AWS IoT
  TwinMaker and Amazon Managed Grafana to be available there.
- **Managed Grafana (CS1).** The CS1 twin deploys an Amazon Managed Grafana
  workspace with the `AWS_SSO` authentication provider, so AWS IAM Identity Center
  must be set up in the account. Without it, set `DEPLOY_MANAGED_GRAFANA=false` in
  `.env`. The twin then has 210 resources instead of the 213 in the paper,
  because Grafana accounts for 3 of them.
- **Quotas.** CS2 creates 201 IoT things and certificates, 211 IAM roles and 209
  Lambda functions. Check that the account has room, for example for the default
  limit of 1,000 IAM roles. CS1 creates 29 roles and 26 functions.

## Narrower permissions

The quick start is deliberately broad. To check or narrow it, use these files:

| File | Content |
| --- | --- |
| [`deployer-policy.json`](deployer-policy.json) | The 104 actions that the deployer's code calls, on all resources. It has 3,520 characters, which is too long for an inline user policy. Create it as a managed policy: `aws iam create-policy --policy-name TwinfraDeployer --policy-document file://deployer-policy.json`, then `aws iam attach-user-policy` with the returned ARN. |
| [`evaluator-policy.json`](evaluator-policy.json) | `iot:DescribeEndpoint`, `iot:Connect` for the client ids `dt-eval-*`, `iot:Publish` for the telemetry topic, `iot:Subscribe` and `iot:Receive` for the feedback topic (reaction path only), and the TwinMaker reads for the visualization path. |
| [AWS permissions](../../digital-twin-manager/docs/aws-permissions.md) | Explains each permission of the deployer, and the policies that the deployer creates for the roles of a twin. |

## Optional: resource count and security audit

The resource count (`digital-twin-evaluator/scripts/resource_inventory.py`) and the
security audit (`digital-twin-manager/scripts/security_audit.py`) only read. Use a
separate read-only user, so the deployer key is not needed:

```bash
aws iam create-user --user-name twinfra-readonly
aws iam attach-user-policy --user-name twinfra-readonly --policy-arn arn:aws:iam::aws:policy/ViewOnlyAccess
aws iam attach-user-policy --user-name twinfra-readonly --policy-arn arn:aws:iam::aws:policy/SecurityAudit
aws iam put-user-policy --user-name twinfra-readonly --policy-name TwinMakerIotReadOnly --policy-document file://readonly-extras-policy.json
aws iam create-access-key --user-name twinfra-readonly
```

[`readonly-extras-policy.json`](readonly-extras-policy.json) adds the TwinMaker
reads and `iot:GetTopicRule`, which the two managed policies do not grant. This is
the combination that produced the stored results.

## Clean up

Remove each twin with `destroy` in the deployer, which also deletes its IAM roles.
Resources that still exist cost money. After the experiments, delete the access
keys and the users:

```bash
aws iam delete-access-key --user-name twinfra-reproduce --access-key-id <KEY_ID>
aws iam delete-user-policy --user-name twinfra-reproduce --policy-name Twinfra
aws iam delete-user --user-name twinfra-reproduce
```
