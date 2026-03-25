import pytest

import time

from testcontainers.core.container import DockerContainer

from spade_fipainterop.network import FipaConnector
from helpers import Pinger, DFSearcher


def pytest_addoption(parser):
    # addresses and names
    parser.addoption("--jade-platform", action="store", default="Platform1")
    parser.addoption("--jade-mtp", action="store", default="http://localhost:7778/acc")
    parser.addoption("--jade-pinger-name", action="store", default="ping1")
    parser.addoption("--platform", action="store", default="Platform2")
    parser.addoption("--mtp", action="store", default="http://localhost:7772/acc")
    parser.addoption("--pinger-name", action="store", default="ping2")
    # ping perdiod, and limit
    parser.addoption("--ping-period", action="store", default="1")
    parser.addoption("--ping-number", action="store", default="5")


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
def ping_conf(pytestconfig):
    """Get the ping period and limit"""
    return (
        float(pytestconfig.getoption("--ping-period")),
        int(pytestconfig.getoption("--ping-number")),
    )

@pytest.fixture(scope="session")
def jade_main(addresses):
    """Start jade container with one pinger agent. return the name of ping agent,
    and mpt of jade platform"""
    # context_path = Path(__file__).parent / "integration" / "jade_container"
    jade_addr = addresses["jade"]
    local_addr = addresses["local"]
    container = (
        DockerContainer("jade:latest")
        #.with_exposed_ports(7778, 1099)
        .with_kwargs(network_mode="host")
        .with_env("LOCAL_AGENT_NAME", jade_addr["pinger-name"])
        .with_env("LOCAL_PLATFORM", jade_addr["platform"])
        .with_env("LOCAL_MTP", jade_addr["mtp"])
        .with_env(
            "REMOTE_AGENT_NAME", f"{local_addr['pinger-name']}@{local_addr['platform']}"
        )
        .with_env("REMOTE_URL", local_addr["mtp"])
        #.waiting_for(HttpWaitStrategy.from_url(jade_addr['mtp']))
    )
    container.start()
    time.sleep(2)
    #port = container.get_exposed_port(7778)
    yield (
        f"{jade_addr['pinger-name']}@{jade_addr['platform']}",
        jade_addr["mtp"] #.replace("7778", str(port))
    )
    print(container.get_logs()[1].decode())
    container.stop()


@pytest.fixture(scope="function")
def ping_server(addresses, ping_conf):
    jade = addresses["jade"]
    addr = addresses["local"]
    period, limit = ping_conf
    conn = FipaConnector(remote_url=jade["mtp"], local_url=addr['mtp'])
    pinger = Pinger(
        conn,
        remote_name=jade["pinger-name"] + "@" + jade["platform"],
        remote_url=jade["mtp"],
        local_name=addr["pinger-name"],
        local_url=addr["mtp"],
        send=True,
        period=period,
        limit=limit,
    )
    conn.app.on_startup.append(pinger.start)
    conn.app.on_cleanup.append(pinger.cleanup)
    yield conn, pinger


@pytest.fixture(scope="function")
def df_search(addresses):
    jade = addresses["jade"]
    addr = addresses["local"]
    conn = FipaConnector(remote_url=jade["mtp"], local_url=addr["mtp"])
    searcher = DFSearcher(
        conn,
        addr["mtp"],
        addr["pinger-name"],
        addr["platform"],
        jade["mtp"],
        jade["platform"],
    )
    conn.app.on_startup.append(searcher.start)
    conn.app.on_cleanup.append(searcher.cleanup)
    yield conn, searcher
