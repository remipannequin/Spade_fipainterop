"""Simple server to demonstrate interoperability with jade."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from asyncio import Queue
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from aiohttp import ClientSession, web, TCPConnector

from lark import Lark, Token, Transformer

logging.basicConfig(level=logging.DEBUG)


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
        self.name = name
        self.addresses = addresses or []

    def __repr__(self):
        return (
            f"(agent-identifier :name {self.name} "
            + f":addresses (sequence {' '.join(self.addresses)} ))"
        )


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
    return dt.strftime("%Y%m%dT%H%M%S")+f"{dt.microsecond // 1000:03d}"


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
        body_lines.append(bd+b"--")

        # final line
        #body_lines.append(b"2")
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
            async with session.post(
                url, data=body, headers=headers
            ) as resp:
                # check that it is OK
                response = await resp.read()
                print(resp, response)


def ping_reply(ping: ACLMessage) -> ACLMessage:
    """Create a ping reply message"""
    pong = ping.create_reply(ACLPerformative.INFORM)
    assert ping.content
    ping_num = ping.content[6:]
    pong.content = "pong_" + ping_num
    return pong


def create_ping(name: str, addr: str) -> ACLMessage:
    """Prepare a ping message"""
    flds = {
        "sender": AID("ping2@Platform2", ["http://localhost:7772/acc"]),
        "receiver": {AID(name, [addr])},
        "protocol": "c2ps-ping",
        "content": "ping",
    }
    return ACLMessage(ACLPerformative.REQUEST, flds)


class FipaConnector(web.Application):
    incomming_message_queue: Queue[ACLMessage]
    outgoing_message_queue: Queue[ACLMessage]
    in_worker: asyncio.Task
    out_worker: asyncio.Task
    test_sender: asyncio.Task

    def __init__(self, url, test = False):
        self.url = url
        self.incomming_message_queue = Queue()
        self.outgoing_message_queue = Queue()
        super().__init__()
        self.add_routes([web.post("/acc", self.handle_message)])
        self.on_startup.append(self.start_message_worker)
        self.on_cleanup.append(self.cleanup_message_worker)
        if test:
            self.on_startup.append(self.start_test_sender)
            self.on_cleanup.append(self.cleanup_test_sender)

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
            self.incomming_message_queue.put_nowait(acl_msg_obj)
        # Retourner OK au client
        return web.Response(status=200, text="<html><body><h1>200 OK</h1></body></html>\r\n")

    async def start_message_worker(self, _):
        """Start the message-processing task"""
        self.in_worker = asyncio.create_task(self.process_incoming_messages())
        self.out_worker = asyncio.create_task(self.process_outgoing_messages())

    async def start_test_sender(self, app):
        self.test_sender = asyncio.create_task(self.send_ping())

    async def cleanup_message_worker(self, _):
        """Stop the message-processing task"""
        self.in_worker.cancel()
        self.out_worker.cancel()
        await asyncio.gather(self.in_worker, self.out_worker, return_exceptions=True)


    async def cleanup_test_sender(self, _):
        self.test_sender.cancel()
        await self.test_sender

    async def process_incoming_messages(self):
        while True:
            try:
                message = await self.incomming_message_queue.get()
                print(f"Received {message.content} from {message.sender}")
                # TODO route message to actual agent !
                if (
                    message.performative == ACLPerformative.REQUEST
                    and message.protocol == "c2ps-ping"
                ):
                    reply = ping_reply(message)
                    print(f"replying {reply.content}")
                    await self.outgoing_message_queue.put(reply)
            except Exception as e:
                print("Error processing incoming message:", e)
            finally:
                self.incomming_message_queue.task_done()

    async def process_outgoing_messages(self):
        while True:
            try:
                msg = await self.outgoing_message_queue.get()
                print("sending outgoing message")
                await send_outgoing_message(msg)
            except Exception as e:
                print("Error processing outgoing message:", e)
            finally:
                self.outgoing_message_queue.task_done()

    async def send_ping(self):
        while True:
            try:
                msg = create_ping("ping1@Platform1", self.url)
                self.outgoing_message_queue.put_nowait(msg)
                print("Creating a ping message")
                await asyncio.sleep(5)
            except Exception as e:
                print("Error sending ping:", e)


def create_ping_server(url:str, test=False):
    app = FipaConnector(url, test=test)
    return app


if __name__ == "__main__":
    web.run_app(create_ping_server("http://hobart:7771/acc", test=True), host="127.0.0.1", port=7772)
