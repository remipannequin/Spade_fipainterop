import pytest

from testcontainers.core.container import DockerContainer


@pytest.fixture(scope="session")
def jade_main():
    # context_path = Path(__file__).parent / "integration" / "jade_container"

    container = (
        DockerContainer("jade:latest")
        #.with_exposed_ports(7778, 1099)
        .with_kwargs(network_mode="host")
        .with_env("LOCAL_AGENT_NAME", "ping1")
        .with_env("REMOTE_AGENT_NAME", "ping2")
        .with_env("REMOTE_URL", "http://localhost:7772")
    )

    container.start()

    host = container.get_container_host_ip()
    #port = container.get_exposed_port(7778)
    port = 7778
    yield f"http://{host}:{port}/acc"

    container.stop()
