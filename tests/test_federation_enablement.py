from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import federate_battery_charger_decision as battery
from scripts import federate_pv_weather as pv


@pytest.fixture(params=[pv, battery], ids=["pv-weather", "battery-charger"])
def enablement(request):
    module = request.param
    if module is pv:
        return SimpleNamespace(
            inject=lambda client, env: pv.inject_env(client, env),
            grant=lambda iam: pv.grant_invoke(iam, "weather-reader"),
            resources=["weather-reader"],
        )
    return SimpleNamespace(
        inject=lambda client, env: battery.inject_env(client, battery.CHARGER_STRATEGY_NAME, env),
        grant=lambda iam: battery.grant_invoke(iam, battery.CHARGER_STRATEGY_NAME, ["grid-reader", "battery-reader"]),
        resources=["grid-reader", "battery-reader"],
    )


def test_environment_updates_preserve_terraform_variables(enablement):
    client = Mock()
    client.get_function_configuration.return_value = {"Environment": {"Variables": {"PARAMETERS": "inputs"}}}
    enablement.inject(client, {"DEVICE_ID": "new-device"})
    assert client.update_function_configuration.call_args.kwargs["Environment"]["Variables"] == {
        "PARAMETERS": "inputs", "DEVICE_ID": "new-device",
    }
    client.get_waiter.return_value.wait.assert_called_once()


def test_matching_environment_is_not_updated_again(enablement):
    client = Mock()
    client.get_function_configuration.return_value = {"Environment": {"Variables": {"DEVICE_ID": "same"}}}
    enablement.inject(client, {"DEVICE_ID": "same"})
    client.update_function_configuration.assert_not_called()


def test_retry_waits_for_pending_lambda_update(enablement):
    client = Mock()
    client.get_function_configuration.side_effect = [
        {"LastUpdateStatus": "InProgress", "Environment": {"Variables": {"DEVICE_ID": "same"}}},
        {"LastUpdateStatus": "Successful", "Environment": {"Variables": {"DEVICE_ID": "same"}}},
    ]
    enablement.inject(client, {"DEVICE_ID": "same"})
    client.get_waiter.return_value.wait.assert_called_once()
    client.update_function_configuration.assert_not_called()


def test_failed_lambda_update_is_retried_even_if_environment_matches(enablement):
    client = Mock()
    client.get_function_configuration.return_value = {
        "LastUpdateStatus": "Failed", "Environment": {"Variables": {"DEVICE_ID": "same"}},
    }
    enablement.inject(client, {"DEVICE_ID": "same"})
    client.update_function_configuration.assert_called_once()


def test_matching_invoke_policy_is_not_updated_again(enablement):
    iam = Mock()
    iam.get_role_policy.return_value = {"PolicyDocument": {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": ["lambda:InvokeFunction"], "Resource": enablement.resources}],
    }}
    enablement.grant(iam)
    iam.put_role_policy.assert_not_called()


def test_missing_invoke_policy_is_created(enablement):
    iam = Mock()
    iam.exceptions.NoSuchEntityException = type("Missing", (Exception,), {})
    iam.get_role_policy.side_effect = iam.exceptions.NoSuchEntityException()
    enablement.grant(iam)
    iam.put_role_policy.assert_called_once()
