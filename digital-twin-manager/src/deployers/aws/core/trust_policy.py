import globals


def service_trust_policy(service_principal):
  """Trust policy for a service role, bound to this AWS account.

  `aws:SourceAccount` prevents the cross-service confused deputy problem: the
  service principal may only assume the role on behalf of resources in this account.
  """
  account_id = globals.aws_sts_client.get_caller_identity()["Account"]
  return {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": service_principal
        },
        "Action": "sts:AssumeRole",
        "Condition": {
          "StringEquals": {
            "aws:SourceAccount": account_id
          }
        }
      }
    ]
  }
