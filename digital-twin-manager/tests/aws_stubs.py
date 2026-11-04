from __future__ import annotations

import sys
import types


AWS_REGION = "eu-west-1"


class ClientError(Exception):
  def __init__(self, response=None, operation_name=None):
    super().__init__(operation_name)
    self.response = response or {"Error": {}}
    self.operation_name = operation_name


class StubAwsClient:
  def __init__(self, region_name: str = AWS_REGION):
    self.meta = types.SimpleNamespace(region_name=region_name)


class StubStsClient(StubAwsClient):
  def get_caller_identity(self):
    return {"Account": "123456789012"}


def install_aws_stubs() -> None:
  boto3 = types.ModuleType("boto3")
  boto3.client = lambda *args, **kwargs: StubAwsClient()
  sys.modules["boto3"] = boto3

  sys.modules.setdefault("botocore", types.ModuleType("botocore"))

  exceptions = types.ModuleType("botocore.exceptions")
  exceptions.ClientError = ClientError
  sys.modules["botocore.exceptions"] = exceptions
