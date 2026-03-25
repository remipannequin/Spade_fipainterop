import logging
from urllib.parse import urlparse
from aiohttp import web
from slixmpp import ComponentXMPP, JID, Message as slixmppMessage
from spade.message import Message

from spade_fipainterop.network import FipaConnector
from spade_fipainterop.fipa import ACLMessage, ACLPerformative, AID

logger = logging.getLogger("FipaBridge")

class FipaBridge(ComponentXMPP):
    def __init__(self, jid, secret, server, conn: FipaConnector, port=5347):
        super().__init__(jid, secret, server, port)
        self.conn = conn
        self.mtp = conn.remote_url
        self.remote_mtp = conn.remote_url
        self.add_event_handler("session_start", self.start)
        self.add_event_handler("message", self.on_message)

    async def start(self, event):
        print("Component started and ready to filter messages")

    async def on_message(self, msg: slixmppMessage):
        """Get an XMPP message and add it to the outgoing queue"""
        in_msg: Message = Message.from_node(msg) # type: ignore
        # put message in FIPA ACL format
        perf = in_msg.get_metadata("performative")
        if not perf:
            logger.warning("received message without the 'performative' metadata.")
            p = ACLPerformative.INFORM
        else:
            p = ACLPerformative(value=perf)
        out_msg = ACLMessage(p, {})
        if in_msg.body:
            out_msg.content = in_msg.body
        if in_msg.thread:
            out_msg.conversation_id = in_msg.thread
        out_msg.sender = AID(in_msg.sender.full, [self.mtp])
        out_msg.add_receiver(AID(in_msg.to.full, [self.remote_mtp]))
        # TODO: ontology and language if they exists
        await self.conn.post_message(out_msg)


    async def transfer_to_xmpp(self):
        """Loop that receive messages from the external system, translate them
        to xmpp format and send them."""
        while True:
            in_msg = await self.conn.get_message()
            from_jid = JID(in_msg.sender.name)
            # body <- content
            for r in in_msg.receiver:
                out_msg = Message()
                out_msg.sender = from_jid
                out_msg.to = JID(r.name)
                out_msg.body = in_msg.content
                out_msg.thread = in_msg.conversation_id
                out_msg.set_metadata("performative", in_msg.performative.value)
                out_msg.set_metadata("from-mtp", in_msg.sender.addresses[0])
                # TODO: set in metadata language, protocol, ontology...
                slixmpp_msg = out_msg.prepare(self)  # type: ignore
                slixmpp_msg.send()


async def run_bridge(url, remote_mtp, remote_platform_name):
    """Run the bridge: web server + xmpp bridge"""
    # Configuration
    jid = "jade.localhost"
    secret = "component_secret"
    server = "localhost"
    mtp = urlparse(url)
    conn = FipaConnector(remote_url=remote_mtp, local_url=url)
    xmpp = FipaBridge(jid, secret, server, conn)
    
    await xmpp.connect()
    runner = web.AppRunner(conn.app)
    await runner.setup()
    site = web.TCPSite(runner, mtp.hostname, mtp.port)
    await site.start()

    # run until xmpp is disconnected
    await xmpp.disconnected
