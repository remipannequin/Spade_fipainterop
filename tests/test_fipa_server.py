from spade_fipainterop.ping_server import create_ping_server, FipaConnector
from urllib.parse import urlparse
from aiohttp import web
import asyncio


async def start_connector(app: web.Application, host, port):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    await asyncio.sleep(30)

def test_ping(jade_main, addresses):
    jade_ag, jade_mtp = jade_main
    addr = addresses["local"]
    mtp = urlparse(addr["mtp"])
    conn, pinger = create_ping_server(
        local_name=f"{addr['pinger-name']}@{addr['platform']}",
        local_url=addr["mtp"],
        remote_name=jade_ag,
        remote_url=jade_mtp,
        send=True,
        limit=5,
    )
    asyncio.run(start_connector(conn.app, mtp.hostname, mtp.port))
    
    assert len(pinger.sent) == 5
    assert len(pinger.delays) == 5
