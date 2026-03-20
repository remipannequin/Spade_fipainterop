"""Simple server to demonstrate interoperability with jade."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from asyncio import Queue
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import StrEnum
from typing import Any

from aiohttp import ClientSession, web, TCPConnector

from lark import Lark, Token, Transformer

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("FIPAConnector")


FIPA_ACL_REPR = "fipa.acl.rep.string.std"

acl_grammar = r"""
// ---------------- ACL MESSAGE ----------------

acl_message: "(" PERFORMATIVE keyword_term* ")"


// ---------------- COLLECTIONS ----------------

?collection: set
          | sequence

set: "(" "set" term* ")"
sequence: "(" "sequence" term* ")"

// ----------------- AID -----------------

agent_id: "(" "agent-identifier" keyword_term* ")"


// ---------------- TERMS ----------------

?term: keyword_term
     | simple_term

keyword_term: KEYWORD simple_term

?simple_term: value
            | collection
            | agent_id

// ---------------- SYMBOLIC ELEMENTS ----------------

?value: NAME
     | STRING
     | NUMBER
     | DATETIME

// ---------------- LEXER ----------------
PERFORMATIVE: "REPLY" | "REQUEST" | "INFORM" | "QUERY" | "PROPOSE"
            | "ACCEPT_PROPOSAL" | "REJECT_PROPOSAL" | "AGREE" | "REFUSE"
            | "FAILURE" | "NOT_UNDERSTOOD" | "CANCEL" | "CONFIRM"
            | "DISCONFIRM" | "SUBSCRIBE" | "UNSUBSCRIBE" | "PROXY"
KEYWORD: ":" NAME
NAME: /[a-zA-Z_][a-zA-Z0-9_-]*/  // variables
DATETIME: /\d{8}T\d{6,9}Z/

STRING: ESCAPED_STRING | ANY_STRING
ANY_STRING: /[^()\s]+/  // any value without parentheses or whitespace
NUMBER: SIGNED_NUMBER

%import common.ESCAPED_STRING
%import common.SIGNED_NUMBER
%import common.WS
%ignore WS

"""

acl_parser = Lark(acl_grammar, start="acl_message")


class ACLPerformative(StrEnum):
    REPLY = "REPLY"
    REQUEST = "REQUEST"
    INFORM = "INFORM"
    QUERY = "QUERY"
    PROPOSE = "PROPOSE"
    ACCEPT_PROPOSAL = "ACCEPT_PROPOSAL"
    REJECT_PROPOSAL = "REJECT_PROPOSAL"
    AGREE = "AGREE"
    REFUSE = "REFUSE"
    FAILURE = "FAILURE"
    NOT_UNDERSTOOD = "NOT_UNDERSTOOD"
    CANCEL = "CANCEL"
    CONFIRM = "CONFIRM"
    DISCONFIRM = "DISCONFIRM"
    SUBSCRIBE = "SUBSCRIBE"
    UNSUBSCRIBE = "UNSUBSCRIBE"
    PROXY = "PROXY"


class AID:
    def __init__(self, name: str, addresses: list[str] | None = None):
        self.name: str = name
        self.addresses: list[str] = addresses or []

    def __repr__(self):
        return (
            f"(agent-identifier :name {self.name} "
            + f":addresses (sequence {' '.join(self.addresses)} ))"
        )

    def localname(self):
        if self.name:
            return self.name.split("@")[0]


class ACLMessage:
    def __init__(self, performative: ACLPerformative, fields: dict[str, Any]):
        self.performative = performative
        self.fields = fields

    @property
    def sender(self) -> AID:
        v = self.fields.get("sender", None)
        if not v:
            raise ValueError("Sender field is missing in ACLMessage")
        return v

    @property
    def receiver(self) -> set[AID]:
        v = self.fields.get("receiver", None)
        if not v:
            raise ValueError("Receiver field is missing in ACLMessage")
        return v

    @property
    def content(self) -> str | None:
        return self.fields.get("content", None)

    @content.setter
    def content(self, value: str):
        self.fields["content"] = value

    @property
    def conversation_id(self) -> str | None:
        return self.fields.get("conversation-id", None)

    @property
    def protocol(self) -> str | None:
        return self.fields.get("protocol")

    def __repr__(self):
        fields = []
        for k, v in self.fields.items():
            if isinstance(v, set):
                v_str = "(set " + " ".join(str(a) for a in v) + ")"
            elif isinstance(v, list):
                v_str = "(sequence " + " ".join(str(a) for a in v) + ")"
            else:
                v_str = str(v)
            fields.append(f":{k} {v_str}")
        return f"({self.performative}\n{'\n'.join(fields)} )"

    def create_reply(self, performative: ACLPerformative):
        """Create a reply message with the same sender/receiver swapped and
        content copied."""
        reply_fields = {k: v for k, v in self.fields.items() if v is not None}
        reply_fields["in-reply-to"] = self.fields.get("reply-with") or self.fields.get(
            "conversation-id", None
        )
        if self.fields.get("receiver"):
            reply_fields["sender"] = next(iter(self.receiver))
        if self.fields.get("sender"):
            reply_fields["receiver"] = {self.sender}
        return ACLMessage(performative, reply_fields)


class FIPA_SL_Transformer(Transformer):

    def start(self, items):
        return items[0]

    def acl_message(self, items):
        perf = items[0]
        fields = {}
        for f in items[1:]:
            key, value = f
            fields[key] = value
        return ACLMessage(perf, fields)

    def keyword_term(self, items):
        key = str(items[0])[1:]  # enlever le ":"
        value = items[1]
        return key, value

    def agent_id(self, items):
        name = None
        addresses = []
        for k, v in items:
            if k == "name":
                name = v
            elif k == "addresses":
                addresses = v
        return AID(name, addresses)

    # Constantes
    def NAME(self, tok: Token):
        return str(tok)

    def PERFORMATIVE(self, tok: Token):
        return ACLPerformative(str(tok))

    def STRING(self, tok: Token):
        return tok.value

    def ESCAPED_STRING(self, tok: Token):
        return str(tok)[1:-1]  # enlever les guillemets

    def NUMBER(self, tok: Token):
        """Convert a token to a number."""
        if "." in str(tok) or "e" in str(tok).lower():
            return float(tok)
        return int(tok)

    def DATETIME(self, tok: Token):
        """Format is YYYYMMDDTHHMMSSZ, we can convert it to a datetime object if needed."""
        return datetime.strptime(str(tok), "%Y%m%dT%H%M%SZ")

    def set(self, items):
        if len(items) == 0:
            return set()
        return set(items)

    def sequence(self, items):
        if len(items) == 0:
            return []
        return list(items)


def read_agent_identifiers(elem: ET.Element[str] | None) -> list[AID]:
    """Parse all the children of the given element that are agent-identifier
    return a single AID, None or a list of AID
    """
    if elem is None:
        return []
    results = []
    for child in elem:
        if child.tag == "agent-identifier":
            results.append(read_agent_identifier(child))
    return results


def read_agent_identifier(elem: ET.Element[str] | None) -> AID | None:
    assert (
        elem is not None and elem.tag == "agent-identifier"
    ), "Expected an agent-identifier element"
    name = None
    addresses = []
    for child in elem:
        if child.tag == "name":
            name = child.text
        elif child.tag == "addresses":
            for addr in child.findall("url"):
                addresses.append(addr.text)
    assert name is not None, "Agent identifier must have a name"
    return AID(name, addresses)


def fipa_datetime(dt=None):
    if not dt:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%S") + f"{dt.microsecond // 1000:03d}"


@dataclass
class ACLEnvelope:
    index: int
    to_ag: list[AID]
    from_ag: list[AID]
    acl_representation: str
    payload_length: int
    intended_receiver: list[AID]
    message: ACLMessage | None
    date: str = field(default_factory=fipa_datetime)


def read_envelope(elt: ET.Element) -> ACLEnvelope:
    return ACLEnvelope(
        index=int(elt.get("index", "1")),
        to_ag=read_agent_identifiers(elt.find("to")),
        from_ag=read_agent_identifiers(elt.find("from")),
        acl_representation=elt.findtext("acl-representation", FIPA_ACL_REPR),
        payload_length=int(elt.findtext("payload-length", "0")),
        intended_receiver=read_agent_identifiers(elt.find("intended-receiver")),
        message=None,
        date=elt.findtext("date", fipa_datetime()),
    )


def write_envelope(evlp: ACLEnvelope) -> bytes:
    """Convert an envelope to an XML string"""
    root = ET.Element("envelope")
    param = ET.SubElement(root, "params")
    param.set("index", str(evlp.index))

    def add_agent_id(elt: ET.Element, aid: AID):
        e = ET.SubElement(elt, "agent-identifier")
        name = ET.SubElement(e, "name")
        name.text = aid.name
        addr_elt = ET.SubElement(e, "addresses")
        for a in aid.addresses:
            ET.SubElement(addr_elt, "url").text = a

    to_elt = ET.SubElement(param, "to")
    for to_ag in evlp.to_ag:
        add_agent_id(to_elt, to_ag)
    from_elt = ET.SubElement(param, "from")
    for from_ag in evlp.from_ag:
        add_agent_id(from_elt, from_ag)
    ET.SubElement(param, "acl-representation").text = evlp.acl_representation
    ET.SubElement(param, "payload-length").text = str(evlp.payload_length)
    ET.SubElement(param, "date").text = evlp.date
    intented_recv = ET.SubElement(param, "intended-receiver")
    for ag in evlp.intended_receiver:
        add_agent_id(intented_recv, ag)
    preamble = b'<?xml version="1.0"?>\n'
    return preamble + ET.tostring(root, encoding="utf-8", method="xml")


def parse_acl_message(text):
    """Parse un message ACL à partir d'une chaîne de texte brute.
    Utilise Lark pour parser le message selon la grammaire FIPA SL définie.
    """
    tree = acl_parser.parse(text)
    transformer = FIPA_SL_Transformer()
    acl_msg_obj = transformer.transform(tree)
    return acl_msg_obj


def prepare_outgoing_message(
    msg: ACLMessage, intended_receiver: AID
) -> tuple[bytes, str]:
    """Prepare the text for the enveloppe and the message"""
    txt_message = str(msg)
    evlp = ACLEnvelope(
        index=1,
        to_ag=list(msg.receiver),
        from_ag=[msg.sender],
        acl_representation=FIPA_ACL_REPR,
        intended_receiver=[intended_receiver],
        message=msg,
        payload_length=len(txt_message),
    )
    return (write_envelope(evlp), txt_message)


async def send_outgoing_message(m: ACLMessage):
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


class FipaConnector(web.Application):
    """Connect to a remote agent platform using the fipa standard to exchange
    messages."""

    _incomming: Queue[ACLMessage]
    _outgoing: Queue[ACLMessage]
    # In addition of the web thread that is responsible for receiving messages,
    # this worker sends outgoing messages (using a POST request)
    out_worker: asyncio.Task

    def __init__(self, url):
        self.url = url
        self._incomming = Queue()
        self._outgoing = Queue()
        super().__init__()
        # TODO use a parameter
        self.add_routes([web.post("/acc", self.handle_message)])
        self.on_startup.append(self.start_message_sender)
        self.on_cleanup.append(self.cleanup_message_sender)

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
                await send_outgoing_message(msg)
            except Exception as e:
                logger.error("Error processing outgoing message:", e)
            finally:
                self._outgoing.task_done()


class Pinger:
    """A client of the connector that send and reply to pings to/from jade"""

    reply_task: asyncio.Task
    sender_task: asyncio.Task
    sent: dict[str, datetime]
    delays: list[timedelta]

    def __init__(
        self,
        connector: FipaConnector,
        local_url: str,
        local_name: str,
        remote_url: str,
        remote_name: str,
        send: bool = True,
        limit: int | None = None,
    ):
        """Create a Pinger that connects to the incomming / outgoing queues
        in the connector."""
        self.conn = connector
        self.local_aid = AID(local_name, [local_url])
        self.remote_aid = AID(remote_name, [remote_url])
        self.send = send
        self.sent = {}
        self.delays = []
        self.limit = limit

    async def start(self, _):
        # install tasks in the connector
        self.reply_task = asyncio.create_task(self.do_reply_task())
        if self.send:
            self.sender_task = asyncio.create_task(self.do_sender_task())
            # self.on_cleanup.append(self.cleanup_test_sender)

    async def cleanup(self, _):
        """Cleanup reply (and sender) tasks"""
        self.reply_task.cancel()
        if not self.sender_task:
            await self.reply_task
        else:
            self.sender_task.cancel()
            await asyncio.gather(self.sender_task, self.reply_task)

    async def do_reply_task(self):
        """The task of getting incomming message and sending reply"""
        while True:
            try:
                message = await self.conn.get_message()
                logger.info(f"Received {message.content} from {message.sender}")
                # TODO route message to actual agent !
                if (
                    message.performative == ACLPerformative.REQUEST
                    and message.protocol == "c2ps-ping"
                ):
                    reply = self.reply(message)
                    logger.info(f"replying {reply.content}")
                    await self.conn._outgoing.put(reply)
                else:
                    # check if this is a reply
                    if message.conversation_id in self.sent:
                        t = self.sent[message.conversation_id]
                        delay = datetime.now() - t
                        # TODO use enveloppe date instead
                        print(f"Got a reply after {delay}")
                        self.delays.append(delay)
                    else:
                        print(message)

            except Exception as e:
                logger.error("Error processing incoming message:", e)
            #finally:
            #    self.conn._incomming.task_done()

    async def do_sender_task(self):
        """Send a ping message every 5 seconds"""
        while True:
            try:
                msg = self.create_ping()
                await self.conn.post_message(msg)
                assert msg.conversation_id, "conversation id not set"
                self.sent[msg.conversation_id] = datetime.now()
                logger.info("Creating a ping message")
                await asyncio.sleep(5)
                if self.limit and len(self.sent) >= self.limit:
                    print("limit reached, stopping...")
                    await self.conn.shutdown()
                    await self.conn.cleanup()
            except Exception as e:
                logger.error("Error sending ping:", e)

    def reply(self, ping: ACLMessage) -> ACLMessage:
        """Create a ping reply message"""
        # no need to know local or remote name here,
        # they are already in the message
        pong = ping.create_reply(ACLPerformative.INFORM)
        assert ping.content
        ping_num = ping.content[6:]
        pong.content = "pong_" + ping_num
        return pong

    def create_ping(self) -> ACLMessage:
        """Prepare a ping message, from local to remote"""
        n = len(self.sent)
        conv_id = f"ping-{self.local_aid.localname()}-{n}"
        flds = {
            "sender": self.local_aid,
            "receiver": {self.remote_aid},
            "protocol": "c2ps-ping",
            "content": f"ping_{n}",
            "conversation-id": conv_id,
        }
        return ACLMessage(ACLPerformative.REQUEST, flds)


def create_ping_server(
    remote_name: str,
    remote_url: str,
    local_name: str,
    local_url: str,
    send=True,
    limit=None,
):
    app = FipaConnector(remote_url)
    pinger = Pinger(
        app,
        remote_name=remote_name,
        remote_url=remote_url,
        local_name=local_name,
        local_url=local_url,
        send=send,
        limit=limit,
    )
    app.on_startup.append(pinger.start)
    app.on_cleanup.append(pinger.cleanup)
    return app, pinger


if __name__ == "__main__":
    web.run_app(
        create_ping_server(
            local_name="ping2@Platform2",
            local_url="http://localhost:7772/acc",
            remote_name="ping1@Platform1",
            remote_url="http://hobart:7778/acc",
            send=True,
        )[0],
        host="127.0.0.1",
        port=7772,
    )
