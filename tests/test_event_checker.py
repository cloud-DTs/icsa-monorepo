import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from tests import support


LAMBDA_ADDRESS = (
    "arn:aws:lambda:eu-central-1:123456789012:"
    "function:CombinedStrategy_pipeline"
)
STATE_MACHINE_ADDRESS = (
    "arn:aws:states:eu-central-1:123456789012:stateMachine:legacy"
)


class EventCheckerTestCase(unittest.TestCase):
    def setUp(self):
        print_patcher = patch("builtins.print")
        print_patcher.start()
        self.addCleanup(print_patcher.stop)

        self.event_checker = support.load_event_checker(
            f"event_checker_for_{self.id().replace('.', '_')}"
        )
        self.event_checker.lambda_client = Mock()
        self.event_checker.sf_client = Mock()
        self.event_checker.ssm_client = Mock()
        self.event_checker.twinmaker_client = Mock()
        self.event_checker.TWINMAKER_WORKSPACE_NAME = "Source-twinmaker"


class TwinMakerValueTests(EventCheckerTestCase):
    def test_unwrap_data_value_handles_nested_lists_and_maps(self):
        wrapped = {
            "listValue": [
                {"doubleValue": 12.5},
                {
                    "mapValue": {
                        "enabled": {"booleanValue": True},
                        "label": {"stringValue": "active"},
                    }
                },
            ]
        }

        self.assertEqual(
            [12.5, {"enabled": True, "label": "active"}],
            self.event_checker.unwrap_data_value(wrapped),
        )
        self.assertEqual(
            {"first": 1, "second": 2},
            self.event_checker.unwrap_data_value(
                {"first": 1, "second": 2}
            ),
        )

    def test_fetch_value_returns_most_recent_history_value(self):
        self.event_checker.twinmaker_client.get_property_value_history.return_value = {
            "propertyValues": [
                {
                    "values": [
                        {"value": {"doubleValue": 12.5}}
                    ]
                }
            ]
        }

        result = self.event_checker.fetch_value(
            "entity",
            "component",
            "power",
        )

        self.assertEqual(12.5, result)
        history_call = (
            self.event_checker.twinmaker_client
            .get_property_value_history
            .call_args
            .kwargs
        )
        self.assertEqual("Source-twinmaker", history_call["workspaceId"])
        self.assertEqual("entity", history_call["entityId"])
        self.assertEqual("component", history_call["componentName"])
        self.assertEqual(["power"], history_call["selectedProperties"])
        self.assertEqual(1, history_call["maxResults"])
        self.assertEqual("DESCENDING", history_call["orderByTime"])
        self.event_checker.twinmaker_client.get_property_value.assert_not_called()

    def test_fetch_value_returns_none_for_empty_history(self):
        self.event_checker.twinmaker_client.get_property_value_history.return_value = {
            "propertyValues": []
        }

        result = self.event_checker.fetch_value(
            "entity",
            "component",
            "power",
        )

        self.assertIsNone(result)
        self.event_checker.twinmaker_client.get_property_value.assert_not_called()

    def test_fetch_value_falls_back_to_latest_property(self):
        self.event_checker.twinmaker_client.get_property_value_history.side_effect = (
            RuntimeError("history unavailable")
        )
        self.event_checker.twinmaker_client.get_property_value.return_value = {
            "propertyValues": {
                "power": {
                    "propertyValue": {
                        "value": {"doubleValue": 9.5}
                    }
                }
            }
        }

        result = self.event_checker.fetch_value(
            "entity",
            "component",
            "power",
        )

        self.assertEqual(9.5, result)
        self.event_checker.twinmaker_client.get_property_value.assert_called_once_with(
            workspaceId="Source-twinmaker",
            entityId="entity",
            componentName="component",
            selectedProperties=["power"],
        )

    def test_fetch_value_propagates_error_when_history_and_fallback_fail(self):
        self.event_checker.twinmaker_client.get_property_value_history.side_effect = (
            RuntimeError("history unavailable")
        )
        self.event_checker.twinmaker_client.get_property_value.side_effect = OSError(
            "latest unavailable"
        )

        with self.assertRaisesRegex(OSError, "latest unavailable"):
            self.event_checker.fetch_value(
                "entity",
                "component",
                "power",
            )


class RegistryTargetTests(EventCheckerTestCase):
    def test_explicit_lambda_target_is_invoked_asynchronously(self):
        payload = {"value": 42}
        expected_response = {"StatusCode": 202}
        self.event_checker.lambda_client.invoke.return_value = expected_response

        response = self.event_checker.invoke_registry_target(
            {"type": "lambda", "address": LAMBDA_ADDRESS},
            payload,
        )

        self.assertEqual(expected_response, response)
        invocation = self.event_checker.lambda_client.invoke.call_args.kwargs
        self.assertEqual(LAMBDA_ADDRESS, invocation["FunctionName"])
        self.assertEqual("Event", invocation["InvocationType"])
        self.assertEqual(
            payload,
            json.loads(invocation["Payload"].decode("utf-8")),
        )
        self.event_checker.sf_client.start_execution.assert_not_called()

    def test_lambda_type_is_inferred_from_arn(self):
        self.event_checker.invoke_registry_target(
            {"address": LAMBDA_ADDRESS},
            {"value": 42},
        )

        self.event_checker.lambda_client.invoke.assert_called_once()
        self.event_checker.sf_client.start_execution.assert_not_called()

    def test_legacy_step_function_target_is_still_supported(self):
        payload = {"value": 42}

        self.event_checker.invoke_registry_target(
            {"addressType": "step-function", "address": STATE_MACHINE_ADDRESS},
            payload,
        )

        self.event_checker.sf_client.start_execution.assert_called_once_with(
            stateMachineArn=STATE_MACHINE_ADDRESS,
            input=json.dumps(payload),
        )
        self.event_checker.lambda_client.invoke.assert_not_called()

    def test_step_function_type_is_inferred_from_arn(self):
        self.event_checker.invoke_registry_target(
            {"address": STATE_MACHINE_ADDRESS},
            {"value": 42},
        )

        self.event_checker.sf_client.start_execution.assert_called_once()
        self.event_checker.lambda_client.invoke.assert_not_called()

    def test_unknown_target_type_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "Unsupported FunctionRegistry target type 'queue'",
        ):
            self.event_checker.invoke_registry_target(
                {
                    "type": "queue",
                    "address": "arn:aws:sqs:eu-central-1:123456789012:queue",
                },
                {"value": 42},
            )


class RegistryLookupTests(EventCheckerTestCase):
    def test_registry_lookup_uses_prefix_and_returns_targets(self):
        targets = [{"type": "lambda", "address": LAMBDA_ADDRESS}]
        self.event_checker.SSM_REGISTRY_PREFIX = "/Source/event-registry"
        self.event_checker.ssm_client.get_parameter.return_value = {
            "Parameter": {"Value": json.dumps({"targets": targets})}
        }

        result = self.event_checker.lookup_registry("production")

        self.assertEqual(targets, result)
        self.event_checker.ssm_client.get_parameter.assert_called_once_with(
            Name="/Source/event-registry/production"
        )

    def test_registry_lookup_is_skipped_without_prefix(self):
        self.event_checker.SSM_REGISTRY_PREFIX = None

        self.assertIsNone(self.event_checker.lookup_registry("production"))
        self.event_checker.ssm_client.get_parameter.assert_not_called()

    def test_missing_registry_entry_falls_back_to_default(self):
        class ParameterNotFound(Exception):
            pass

        self.event_checker.SSM_REGISTRY_PREFIX = "/Source/event-registry"
        self.event_checker.ssm_client.exceptions = SimpleNamespace(
            ParameterNotFound=ParameterNotFound
        )
        self.event_checker.ssm_client.get_parameter.side_effect = ParameterNotFound

        self.assertIsNone(self.event_checker.lookup_registry("production"))


class FireActionTests(EventCheckerTestCase):
    def test_registry_fans_out_same_payload_to_every_target(self):
        event_config = {
            "action": {
                "type": "lambda",
                "functionName": "production",
            }
        }
        input_parameters = {"power": 12.5, "minimum": 0}
        targets = [
            {"type": "lambda", "address": LAMBDA_ADDRESS},
            {"type": "step_function", "address": STATE_MACHINE_ADDRESS},
        ]
        payload = {"e": event_config, **input_parameters}

        with patch.object(
            self.event_checker,
            "invoke_registry_target",
        ) as invoke:
            self.event_checker.fire_action(
                event_config,
                input_parameters,
                targets,
            )

        self.assertEqual(
            [
                call(targets[0], payload),
                call(targets[1], payload),
            ],
            invoke.call_args_list,
        )
        self.event_checker.lambda_client.invoke.assert_not_called()
        self.event_checker.sf_client.start_execution.assert_not_called()

    def test_default_action_invokes_twin_lambda_when_registry_is_empty(self):
        event_config = {
            "action": {
                "type": "lambda",
                "functionName": "production",
            }
        }
        input_parameters = {"power": 12.5}

        self.event_checker.fire_action(
            event_config,
            input_parameters,
            None,
        )

        invocation = self.event_checker.lambda_client.invoke.call_args.kwargs
        self.assertEqual("Source-production", invocation["FunctionName"])
        self.assertEqual("Event", invocation["InvocationType"])
        self.assertEqual(
            {"e": event_config, "power": 12.5},
            json.loads(invocation["Payload"].decode("utf-8")),
        )

    def test_default_feedback_action_keeps_legacy_step_function_flow(self):
        event_config = {
            "action": {
                "type": "lambda",
                "functionName": "production",
                "feedback": {"topic": "Source/iot-data"},
            }
        }
        action_arn = (
            "arn:aws:lambda:eu-central-1:123456789012:function:Source-production"
        )
        self.event_checker.LAMBDA_CHAIN_STEP_FUNCTION_ARN = STATE_MACHINE_ADDRESS
        self.event_checker.EVENT_FEEDBACK_LAMBDA_FUNCTION_ARN = (
            "arn:aws:lambda:eu-central-1:123456789012:function:event-feedback"
        )
        self.event_checker.lambda_client.get_function.return_value = {
            "Configuration": {"FunctionArn": action_arn}
        }

        self.event_checker.fire_action(event_config, {"power": 12.5}, None)

        self.event_checker.lambda_client.get_function.assert_called_once_with(
            FunctionName="Source-production"
        )
        execution = (
            self.event_checker.sf_client.start_execution.call_args.kwargs
        )
        self.assertEqual(STATE_MACHINE_ADDRESS, execution["stateMachineArn"])
        self.assertEqual(
            {
                "LambdaAArn": action_arn,
                "LambdaBArn": (
                    "arn:aws:lambda:eu-central-1:123456789012:"
                    "function:event-feedback"
                ),
                "InputData": {"e": event_config, "power": 12.5},
            },
            json.loads(execution["input"]),
        )


class EventEvaluationTests(EventCheckerTestCase):
    def test_decimal_constant_is_not_treated_as_twinmaker_property_path(self):
        with patch.object(self.event_checker, "fetch_value") as fetch_value:
            result = self.event_checker.resolve_condition_value("DOUBLE(1.25)")

        self.assertEqual(1.25, result)
        fetch_value.assert_not_called()

    def test_only_matching_conditions_fire_actions(self):
        matching = {
            "condition": "entity.component.power > DOUBLE(2.0)",
            "action": {
                "type": "lambda",
                "functionName": "production",
                "inputParameters": [],
            },
        }
        not_matching = {
            "condition": "entity.component.power < DOUBLE(2.0)",
            "action": {
                "type": "lambda",
                "functionName": "status",
                "inputParameters": [],
            },
        }
        self.event_checker.DIGITAL_TWIN_INFO["config_events"] = [
            matching,
            not_matching,
        ]

        with (
            patch.object(
                self.event_checker,
                "lookup_registry",
                return_value=[{"type": "lambda", "address": LAMBDA_ADDRESS}],
            ) as lookup,
            patch.object(self.event_checker, "fire_action") as fire_action,
            patch.object(
                self.event_checker,
                "fetch_value",
                return_value=3.0,
            ),
        ):
            self.event_checker.lambda_handler({"power": 3.0}, None)

        lookup.assert_called_once_with("production")
        fire_action.assert_called_once_with(
            matching,
            {},
            [{"type": "lambda", "address": LAMBDA_ADDRESS}],
        )

    def test_irrelevant_property_update_skips_condition(self):
        event_config = {
            "condition": "entity.component.power > DOUBLE(2.0)",
            "action": {
                "type": "lambda",
                "functionName": "production",
                "inputParameters": [],
            },
        }
        self.event_checker.DIGITAL_TWIN_INFO["config_events"] = [event_config]

        with (
            patch.object(self.event_checker, "fetch_value") as fetch_value,
            patch.object(self.event_checker, "lookup_registry") as lookup,
            patch.object(self.event_checker, "fire_action") as fire_action,
        ):
            self.event_checker.lambda_handler({"temperature": 20.0}, None)

        fetch_value.assert_not_called()
        lookup.assert_not_called()
        fire_action.assert_not_called()

    def test_input_parameters_mix_constants_and_twinmaker_values(self):
        event_config = {
            "action": {
                "inputParameters": [
                    {"name": "minimum", "value": 0},
                    {
                        "name": "power",
                        "id": "entity.component.power",
                    },
                ]
            }
        }

        with patch.object(
            self.event_checker,
            "fetch_value",
            return_value=12.5,
        ) as fetch_value:
            result = self.event_checker.resolve_input_parameters(event_config)

        self.assertEqual({"minimum": 0, "power": 12.5}, result)
        fetch_value.assert_called_once_with("entity", "component", "power")


if __name__ == "__main__":
    unittest.main()
