import json
import os
import boto3


def _payload_value(strategy_result):
    if isinstance(strategy_result, dict) and "strategyResult" in strategy_result:
        strategy_result = strategy_result["strategyResult"]

    if isinstance(strategy_result, dict) and "body" in strategy_result:
        strategy_result = strategy_result["body"]

    if isinstance(strategy_result, str):
        try:
            return json.loads(strategy_result)
        except json.JSONDecodeError:
            return strategy_result

    return strategy_result


def publish_feedback(strategy_result):
    payload = json.dumps(_payload_value(strategy_result))

    feedback_type = os.environ.get('FEEDBACK_TYPE', 'INTERNAL').upper()
    topic = os.environ.get('FEEDBACK_TOPIC', 'default/topic')

    if feedback_type == "INTERNAL":
        iot_client = boto3.client('iot-data')
        iot_client.publish(topic=topic, qos=1, payload=payload)

    elif feedback_type == "EXTERNAL":
        import paho.mqtt.client as mqtt

        broker_url = os.environ.get('BROKER_URL')
        broker_port = int(os.environ.get('BROKER_PORT', 1883))
        username = os.environ.get('BROKER_USERNAME')
        password = os.environ.get('BROKER_PASSWORD')

        if not broker_url:
            raise ValueError("BROKER_URL is required for external feedback")

        client = mqtt.Client()
        if username and password:
            client.username_pw_set(username, password)
        if os.environ.get('USE_TLS', 'false').lower() == 'true':
            client.tls_set()

        connected = False
        loop_started = False
        try:
            client.connect(broker_url, broker_port, 60)
            connected = True
            client.loop_start()
            loop_started = True
            result = client.publish(topic, payload, qos=1)
            result.wait_for_publish(timeout=30)
        finally:
            if loop_started:
                client.loop_stop()
            if connected:
                client.disconnect()

    else:
        raise ValueError(f"Unsupported feedback type: {feedback_type}")

    return {
        'statusCode': 200,
        'body': json.dumps('Feedback sent successfully')
    }


def lambda_handler(event, context):
    return publish_feedback(event)
