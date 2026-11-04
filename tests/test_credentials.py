import importlib
import json
from unittest.mock import Mock

import pytest


module = importlib.import_module("simulator.SimulationLoop")


@pytest.fixture
def factory(monkeypatch, tmp_path):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "config_credentials.json"
    path.write_text(json.dumps({"aws_access_key_id": "file-key", "aws_secret_access_key": "file-secret", "aws_region": "eu-west-1", "aws_session_token": "file-token"}))
    monkeypatch.setattr(module, "CREDENTIALS_PATH", str(path))
    client = Mock()
    monkeypatch.setattr(module.boto3, "client", client)
    return client


def test_temporary_file_credentials_include_the_session_token(factory):
    module._create_iot_client(None)
    assert factory.call_args.kwargs["aws_session_token"] == "file-token"


def test_environment_credentials_use_the_sdk_provider_chain_before_a_legacy_file(factory, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "env-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "env-token")
    monkeypatch.setenv("AWS_REGION", "eu-central-1")
    module._create_iot_client(None)
    assert factory.call_args.kwargs == {"region_name": "eu-central-1"}


def test_incomplete_environment_credentials_do_not_mix_with_a_file(factory, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "env-key")
    with pytest.raises(ValueError, match="together"):
        module._create_iot_client(None)
    factory.assert_not_called()


def test_explicit_profile_keeps_its_own_region_selection(factory, monkeypatch):
    monkeypatch.setenv("AWS_PROFILE", "test-profile")
    module._create_iot_client(None)
    assert factory.call_args.kwargs == {}
