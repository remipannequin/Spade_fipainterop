import pytest

from testcontainers.core.container import DockerContainer


def pytest_addoption(parser):
    parser.addoption("--jade-platform", action="store", default="Platform1")
    parser.addoption("--jade-mtp", action="store", default="http://localhost:7778/acc")
    parser.addoption("--jade-pinger-name", action="store", default="ping1")
    parser.addoption("--platform", action="store", default="Platform2")
    parser.addoption("--mtp", action="store", default="http://localhost:7772/acc")
    parser.addoption("--pinger-name", action="store", default="ping2")


@pytest.fixture(scope="session")
def addresses(pytestconfig):
    return {
        "jade": {
            "platform": pytestconfig.getoption("--jade-platform"),
            "mtp": pytestconfig.getoption("--jade-mtp"),
            "pinger-name": pytestconfig.getoption("--jade-pinger-name"),
        },
        "local": {
            "platform": pytestconfig.getoption("--platform"),
            "mtp": pytestconfig.getoption("--mtp"),
            "pinger-name": pytestconfig.getoption("--pinger-name"),
        },
    }


@pytest.fixture(scope="session")
def jade_main(addresses):
    """Start jade container with one pinger agent. return the name of ping agent,
    and mpt of jade platform"""
    # context_path = Path(__file__).parent / "integration" / "jade_container"
    jade_addr = addresses["jade"]
    local_addr = addresses["local"]
    container = (
        DockerContainer("jade:latest")
        # .with_exposed_ports(7778, 1099)
        .with_kwargs(network_mode="host")
        .with_env("LOCAL_AGENT_NAME", jade_addr["pinger-name"])
        .with_env("LOCAL_PLATFORM", jade_addr["platform"])
        .with_env("LOCAL_MTP", jade_addr["mtp"])
        .with_env(
            "REMOTE_AGENT_NAME", f"{local_addr['pinger-name']}@{local_addr['platform']}"
        )
        .with_env("REMOTE_URL", local_addr["mtp"])
    )
    container.start()

    yield (
        f"{jade_addr['pinger-name']}@{jade_addr['platform']}",
        jade_addr["mtp"],
    )

    container.stop()
