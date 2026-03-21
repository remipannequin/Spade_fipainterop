"""Simple server to demonstrate interoperability with jade."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from asyncio import Queue

from aiohttp import ClientSession, web, TCPConnector

from spade_fipainterop.fipa import ACLMessage, acl_parser, read_envelope, FIPA_SL_Transformer, prepare_outgoing_message

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("FIPAConnector")



class FipaConnector:
    """Connect to a remote agent platform using the fipa standard to exchange
    messages."""

    _incomming: Queue[ACLMessage]
    _outgoing: Queue[ACLMessage]
    # In addition of the web thread that is responsible for receiving messages,
    # this worker sends outgoing messages (using a POST request)
    out_worker: asyncio.Task
    app: web.Application

    def __init__(self, url):
        self.url = url
        self._incomming = Queue()
        self._outgoing = Queue()
        super().__init__()
        self.app = web.Application()
        # TODO use a parameter
        self.app.add_routes([web.post("/acc", self.handle_message)])
        self.app.on_startup.append(self.start_message_sender)
        self.app.on_cleanup.append(self.cleanup_message_sender)

    async def get_message(self) -> ACLMessage:
        """Get the next incomming message"""
        msg = await self._incomming.get()
        self._incomming.task_done()
        return msg

    async def post_message(self, msg: ACLMessage):
        self._outgoing.put_nowait(msg)

    async def handle_message(self, request):
        # Vérifie que c'est un POST
        if request.method != "POST":
            return web.Response(status=405, text="Method Not Allowed")

        # Lecture du corps multipart
        reader = await request.multipart()

        xml_part = None
        text_part = None
        parts: list[tuple[str, str]] = []
        async for part in reader:
            content_type = part.headers.get("Content-Type", "")
            parts.append((content_type, await part.text()))

        # first part must be envelope XML
        if len(parts) == 0 or not parts[0][0].startswith("application/xml"):
            return web.Response(status=400, text="Bad Request: missing XML envelope")
        xml_part = parts[0][1]
        envelope = ET.fromstring(xml_part)
        # print(ET.tostring(envelope))
        params = []
        for child in envelope.findall("params"):
            params.append(read_envelope(child))
        for p in params:
            if len(parts) < 2 and not parts[1][0].startswith("text/plain"):
                return web.Response(
                    status=400, text=f"Bad Request: missing ACL message part {p.index}"
                )
            if p.acl_representation != "fipa.acl.rep.string.std":
                return web.Response(
                    status=400,
                    text=f"Bad Request: unsupported ACL representation {p.acl_representation}",
                )
            text_part = parts[1][1]
            tree = acl_parser.parse(text_part)
            transformer = FIPA_SL_Transformer()
            acl_msg_obj = transformer.transform(tree)
            p.message = acl_msg_obj
            self._incomming.put_nowait(acl_msg_obj)
        # Retourner OK au client
        return web.Response(
            status=200, text="<html><body><h1>200 OK</h1></body></html>\r\n"
        )

    async def send_outgoing_message(self, m: ACLMessage):
        """Send an ACL message"""
        # get the content
        for intended_receiver in m.receiver:
            xml_part, txt_part = prepare_outgoing_message(m, intended_receiver)
            # get the address TODO: address list
            addresses = intended_receiver.addresses
            assert len(addresses), "Outgoing message with no address"
            # prepare the POST request
            # We don't use a MultiPartWriter because jade's MTP suck.
            boundary = "d24295d68ce15f23a32ca2733ac862e"
            bd = f"--{boundary}".encode("iso-8859-1")
            body_lines: list[bytes] = []
            # This is old, and maybe unnecessary...
            body_lines.append(b"This is not part of the MIME multipart encoded message.")

            # Envelope (XML)
            body_lines.append(bd)
            body_lines.append(b"Content-Type: application/xml")
            body_lines.append(xml_part)

            # ACL message
            body_lines.append(bd)
            body_lines.append(b"Content-Type: application/text")
            body_lines.append(txt_part.encode("iso-8859-1"))

            # multipart end
            body_lines.append(bd + b"--")

            # final line
            # body_lines.append(b"2")
            crlf = "\r\n".encode("iso-8859-1")
            body = crlf.join(body_lines)
            url = addresses[0]

            # JADE MTP parser search double quotes to get the boundary, need to add them
            headers = {
                "Content-Type": f'multipart/mixed; boundary="{boundary}"',
                "Cache-Control": "no-cache",
                "Mime-Version": "1.0",
                "Connection": "close",
                "Host": url.split("//")[-1],
            }
            connector = TCPConnector(force_close=True)
            async with ClientSession(connector=connector) as session:
                logger.debug(f"POST message to {url}")
                async with session.post(url, data=body, headers=headers) as resp:
                    # check that it is OK
                    response = await resp.read()
                    logger.debug(f"Got reply: {response}")

    async def start_message_sender(self, _):
        """Start the message-processing task"""
        self.out_worker = asyncio.create_task(self.process_outgoing_messages())

    async def cleanup_message_sender(self, _):
        """Stop the message-processing task"""
        self.out_worker.cancel()
        await self.out_worker

    async def process_outgoing_messages(self):
        while True:
            msg = await self._outgoing.get()
            logger.info("sending outgoing message")
            try:
                await self.send_outgoing_message(msg)
            except Exception as e:
                logger.error("Error processing outgoing message:", e)
            finally:
                self._outgoing.task_done()


