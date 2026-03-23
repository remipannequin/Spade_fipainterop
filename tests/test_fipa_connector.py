
from urllib.parse import urlparse
from aiohttp import web
import asyncio


async def start_connector(app: web.Application, host, port, timeout):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    await asyncio.sleep(timeout)

def test_ping(jade_main, addresses, ping_server, ping_conf):
    jade_ag, jade_mtp = jade_main
    period, limit = ping_conf
    max_t = (period*1.2) * (limit+2)
    addr = addresses["local"]
    mtp = urlparse(addr["mtp"])
    conn, pinger = ping_server
    print(f"running ping test for {max_t} seconds...")
    asyncio.run(start_connector(conn.app, mtp.hostname, mtp.port, timeout=max_t))
    # check all ping sent were replied
    assert len(pinger.sent) == limit
    assert len(pinger.delays) == limit
    # check a reasonable 100ms max delay
    assert all([d.microseconds < 100000 for d in pinger.delays])

def test_df_search(jade_main, addresses, df_search):
    jade_ag, jade_mtp = jade_main
    addr = addresses["local"]
    mtp = urlparse(addr["mtp"])
    conn, searcher = df_search
    print("running df search for 5 seconds...")
    asyncio.run(start_connector(conn.app, mtp.hostname, mtp.port, timeout=5))
    assert searcher.result
    