import io
import json
import unittest
from unittest.mock import Mock, patch

from tests import support  # noqa: F401
from collector import lambda_function as collector


def parameter_data(**overrides):
    data = {
        "name": "power",
        "dataType": "DOUBLE",
        "strategy_name": "production",
        "hot_reader_arn": "arn:aws:lambda:eu-central-1:123456789012:function:hot-reader",
        "region": "eu-central-1",
        "workspace_id": "Source-twinmaker",
        "entity_id": "entity",
        "component_name": "component",
        "property_name": "power",
    }
    data.update(overrides)
    return data


class ParameterInfoTests(unittest.TestCase):
    def test_configured_zero_is_used_without_invoking_hot_reader(self):
        parameter = collector.ParameterInfo.parseInfo(parameter_data(value=0))

        with patch.object(collector.boto3, "client") as boto_client:
            parameter.fetch_value()

        self.assertEqual(0, parameter.value)
        boto_client.assert_not_called()

    def test_hot_reader_response_sets_parameter_value_and_payload(self):
        lambda_client = Mock()
        lambda_client.invoke.return_value = {
            "Payload": io.BytesIO(
                json.dumps(
                    {
                        "propertyValues": {
                            "power": {
                                "propertyValue": {
                                    "value": {"doubleValue": 12.5}
                                }
                            }
                        }
                    }
                ).encode("utf-8")
            )
        }
        parameter = collector.ParameterInfo.parseInfo(parameter_data())

        with patch.object(
            collector.boto3,
            "client",
            return_value=lambda_client,
        ) as client_factory:
            parameter.fetch_value()

        self.assertEqual(12.5, parameter.value)
        client_factory.assert_called_once_with("lambda", region_name="eu-central-1")
        invocation = lambda_client.invoke.call_args.kwargs
        self.assertEqual(parameter.hot_reader_arn, invocation["FunctionName"])
        self.assertEqual("RequestResponse", invocation["InvocationType"])
        self.assertEqual(
            {
                "workspaceId": "Source-twinmaker",
                "entityId": "entity",
                "componentName": "component",
                "selectedProperties": ["power"],
                "properties": {
                    "power": {
                        "definition": {
                            "dataType": {"type": "DOUBLE"}
                        }
                    }
                },
            },
            json.loads(invocation["Payload"].decode("utf-8")),
        )

    def test_hot_reader_function_error_is_propagated(self):
        lambda_client = Mock()
        lambda_client.invoke.return_value = {
            "FunctionError": "Unhandled",
            "Payload": io.BytesIO(
                json.dumps({"errorMessage": "reader failed"}).encode("utf-8")
            ),
        }
        parameter = collector.ParameterInfo.parseInfo(parameter_data())

        with patch.object(collector.boto3, "client", return_value=lambda_client):
            with self.assertRaisesRegex(RuntimeError, "reader failed"):
                parameter.fetch_value()


class CollectorTests(unittest.TestCase):
    def setUp(self):
        print_patcher = patch("builtins.print")
        print_patcher.start()
        self.addCleanup(print_patcher.stop)

    def test_collect_values_selects_triggered_pipeline_and_fetches_all_its_inputs(self):
        parameter_info = {
            "CombinedStrategy": [
                parameter_data(value=12.5),
                parameter_data(
                    name="charge",
                    dataType="INTEGER",
                    strategy_name="status",
                    property_name="charge",
                    value=80,
                ),
            ],
            "UnrelatedStrategy": [
                parameter_data(strategy_name="temperature", value=22.0)
            ],
        }
        event = {"e": {"action": {"functionName": "production"}}}

        with patch.object(collector, "PARAMETER_INFO", parameter_info):
            result = collector.collect_values(event)

        self.assertEqual(
            {
                "CombinedStrategy": {
                    "production": {"power": 12.5},
                    "status": {"charge": 80},
                }
            },
            result,
        )

    def test_lambda_handler_keeps_legacy_status_code_body_contract(self):
        values = {"CombinedStrategy": {"production": {"power": 12.5}}}

        with patch.object(collector, "collect_values", return_value=values):
            result = collector.lambda_handler({"e": {}}, None)

        self.assertEqual(200, result["statusCode"])
        self.assertEqual(values, json.loads(result["body"]))


if __name__ == "__main__":
    unittest.main()
