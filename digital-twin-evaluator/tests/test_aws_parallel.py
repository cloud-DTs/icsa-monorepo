from concurrent.futures import ThreadPoolExecutor
from threading import get_ident

from digital_twin_evaluation.aws import AwsTelemetryBackend
from digital_twin_evaluation.deployment import load_deployment
from test_aws import FakeSession


def test_connection_pool_matches_configured_parallelism(deployment_dir):
    session = FakeSession()
    backend = AwsTelemetryBackend(
        load_deployment(deployment_dir), 3, session=session, max_pool_connections=32,
    )
    assert backend.sdk_config.max_pool_connections == 32
    assert session.calls[0][1]["config"].retries["total_max_attempts"] == 1


def test_ingestion_clients_are_created_on_the_main_thread_and_reused(deployment_dir):
    owner = get_ident()

    class MainThreadSession(FakeSession):
        def client(self, service, **kwargs):
            assert get_ident() == owner, "AWS client was constructed inside a worker"
            return super().client(service, **kwargs)

    session = MainThreadSession()
    backend = AwsTelemetryBackend(
        load_deployment(deployment_dir), 3, session=session,
        max_pool_connections=4, mode="ingestion",
    )
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda number: backend.write("ingestion", {"sequence": number}), range(8)))
    assert [service for service, _ in session.calls] == ["lambda", "iot-data"]
    assert len(session.iot_client.calls) == 8
