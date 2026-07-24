import json
import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

from tests import support  # noqa: F401
from feedback import lambda_function as feedback


def mqtt_modules(client_factory):
    paho_module = types.ModuleType("paho")
    paho_module.__path__ = []
    mqtt_module = types.ModuleType("paho.mqtt")
    mqtt_module.__path__ = []
    client_module = types.ModuleType("paho.mqtt.client")
    client_module.Client = client_factory
    paho_module.mqtt = mqtt_module
    mqtt_module.client = client_module
    return {
        "paho": paho_module,
        "paho.mqtt": mqtt_module,
        "paho.mqtt.client": client_module,
    }


class FeedbackPayloadTests(unittest.TestCase):
    def test_payload_value_supports_plain_and_legacy_results(self):
        cases = [
            ({"consumption": 7.5}, {"consumption": 7.5}),
            (
                {"statusCode": 200, "body": json.dumps({"consumption": 7.5})},
                {"consumption": 7.5},
            ),
            (
                {
                    "strategyResult": {
                        "statusCode": 200,
                        "body": json.dumps({"consumption": 7.5}),
                    }
                },
                {"consumption": 7.5},
            ),
            ({"body": "not-json"}, "not-json"),
        ]

        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(expected, feedback._payload_value(source))


class InternalFeedbackTests(unittest.TestCase):
    def test_internal_feedback_publishes_normalized_json_to_iot(self):
        iot_client = Mock()

        with (
            patch.dict(
                os.environ,
                {
                    "FEEDBACK_TYPE": "INTERNAL",
                    "FEEDBACK_TOPIC": "Battery/iot-data",
                },
                clear=True,
            ),
            patch.object(
                feedback.boto3,
                "client",
                return_value=iot_client,
            ) as client_factory,
        ):
            result = feedback.publish_feedback(
                {"body": json.dumps({"consumption": 7.5})}
            )

        client_factory.assert_called_once_with("iot-data")
        publish_call = iot_client.publish.call_args.kwargs
        self.assertEqual("Battery/iot-data", publish_call["topic"])
        self.assertEqual(1, publish_call["qos"])
        self.assertEqual({"consumption": 7.5}, json.loads(publish_call["payload"]))
        self.assertEqual(200, result["statusCode"])

    def test_unknown_feedback_type_fails_fast(self):
        with patch.dict(
            os.environ,
            {"FEEDBACK_TYPE": "UNKNOWN"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported feedback type"):
                feedback.publish_feedback({"value": 1})


class ExternalFeedbackTests(unittest.TestCase):
    def test_external_feedback_uses_credentials_tls_and_waits_for_publish(self):
        publish_result = Mock()
        mqtt_client = Mock()
        mqtt_client.publish.return_value = publish_result
        client_factory = Mock(return_value=mqtt_client)

        with (
            patch.dict(sys.modules, mqtt_modules(client_factory)),
            patch.dict(
                os.environ,
                {
                    "FEEDBACK_TYPE": "EXTERNAL",
                    "FEEDBACK_TOPIC": "external/topic",
                    "BROKER_URL": "broker.example.com",
                    "BROKER_PORT": "8883",
                    "BROKER_USERNAME": "user",
                    "BROKER_PASSWORD": "password",
                    "USE_TLS": "true",
                },
                clear=True,
            ),
        ):
            feedback.publish_feedback({"value": 42})

        client_factory.assert_called_once_with()
        mqtt_client.username_pw_set.assert_called_once_with("user", "password")
        mqtt_client.tls_set.assert_called_once_with()
        mqtt_client.connect.assert_called_once_with("broker.example.com", 8883, 60)
        mqtt_client.loop_start.assert_called_once_with()
        mqtt_client.publish.assert_called_once_with(
            "external/topic",
            json.dumps({"value": 42}),
            qos=1,
        )
        publish_result.wait_for_publish.assert_called_once_with(timeout=30)
        mqtt_client.loop_stop.assert_called_once_with()
        mqtt_client.disconnect.assert_called_once_with()

    def test_external_feedback_does_not_disconnect_when_connect_fails(self):
        mqtt_client = Mock()
        mqtt_client.connect.side_effect = OSError("connection refused")
        client_factory = Mock(return_value=mqtt_client)

        with (
            patch.dict(sys.modules, mqtt_modules(client_factory)),
            patch.dict(
                os.environ,
                {
                    "FEEDBACK_TYPE": "EXTERNAL",
                    "BROKER_URL": "broker.example.com",
                },
                clear=True,
            ),
        ):
            with self.assertRaisesRegex(OSError, "connection refused"):
                feedback.publish_feedback({"value": 42})

        mqtt_client.loop_start.assert_not_called()
        mqtt_client.loop_stop.assert_not_called()
        mqtt_client.disconnect.assert_not_called()


if __name__ == "__main__":
    unittest.main()

