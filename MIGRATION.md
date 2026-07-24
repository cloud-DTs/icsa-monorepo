# Migration Guide: Step Functions to Pipeline Lambda

This guide is for existing federation deployments created with the previous architecture. For a new deployment, follow [README.md](README.md).

## What changed

Previously, every new federated strategy deployed three Lambda functions coordinated by an AWS Step Functions state machine:

```text
Event checker
    -> Step Functions
        -> collector Lambda
        -> strategy Lambda
        -> feedback Lambda
```

The new architecture deploys one Lambda per federated strategy. Collector, strategy, and feedback remain separate Python modules inside its deployment package:

```text
Event checker
    -> pipeline Lambda
        -> collect()
        -> strategy()
        -> feedback()
```

The SSM event registry target changes with it:

```text
Before:
{"targets":[{"address":"arn:aws:states:...:stateMachine:ConsumptionStrategy-workflow"}]}

After:
{"targets":[{"type":"lambda","address":"arn:aws:lambda:...:function:ConsumptionStrategy_pipeline"}]}
```

## Migration

Recreate the generated infrastructure:

```bash
terraform destroy
terraform apply
```
