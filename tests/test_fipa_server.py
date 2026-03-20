from spade_fipainterop.ping_server import create_ping_server
from aiohttp import web


def test_ping(jade_main):
    url = jade_main
    web.run_app(create_ping_server(url, test=True), host="127.0.0.1", port=7772)
    
