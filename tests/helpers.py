import asyncio
import re
import logging
from datetime import datetime, timedelta
from spade_fipainterop.network import FipaConnector
from spade_fipainterop.fipa import AID, ACLMessage, ACLPerformative
from spade_fipainterop.management import DFAgentDescription, DFSearch, Action

logger = logging.getLogger("FIPAConnector")


def assert_equal_ignore_whitespace(actual: str, expected: str):
    """
    Compare two strings ignoring all whitespace (spaces, tabs, newlines).
    """

    def normalize(s):
        return re.sub(r"\s+", " ", s).strip()

    assert normalize(actual) == normalize(expected), (
        f"Strings differ ignoring whitespace:\n"
        f"Actual  : {actual!r}\n"
        f"Expected: {expected!r}"
    )


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
        period: float = 1.0,
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
        self.period = period

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
            # finally:
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
                await asyncio.sleep(self.period)
                if self.limit and len(self.sent) >= self.limit:
                    print("limit reached, stopping...")
                    await self.conn.app.shutdown()
                    await self.conn.app.cleanup()
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


class DFSearcher:
    def __init__(
        self,
        connector: FipaConnector,
        local_url: str,
        local_name: str,
        local_platform: str,
        remote_url: str,
        remote_platform: str,
    ):
        """Create a Pinger that connects to the incomming / outgoing queues
        in the connector."""
        self.conn = connector
        self.local_aid = AID(local_name+"@"+local_platform, [local_url])
        self.remote_df_aid = AID("df@" + remote_platform, [remote_url])
        self.result = None

    async def start(self, _):
        # install tasks in the connector
        self.sender_task = asyncio.create_task(self.do_sender_task())

    async def cleanup(self, _):
        """Cleanup reply (and sender) tasks"""
        self.sender_task.cancel()
        await self.sender_task

    async def do_sender_task(self):
        """"""
        try:
            msg = self.create_search_msg()
            await self.conn.post_message(msg)
            reply = await self.conn.get_message()
            ct = reply.content
            self.reply = reply
            if reply.performative == ACLPerformative.INFORM and ct :
                self.result = self.decode_search_reply(ct)
            else:
                print(reply)
        except Exception as e:
            logger.error("Error sending ping:", e)

    def create_search_msg(self) -> ACLMessage:
        """
        performative: REQUEST
        protocol: fipa-request
        ontology: FIPA-Agent-Management
        language: fipa-sl0

        Exemple of content:

        ((action
         (agent-identifier
            :name df@Platform1
            :addresses (sequence http://localhost:7778/acc))
         (search
            (df-agent-description
                :services
                (set
                    (service-description
                    :name Ping
                    :type Test-Service)))
            (search-constraints
                :max-results -1))))

        """

        dfad = DFAgentDescription()
        dfad.add_service(type="Test-Service", name="Ping")
        act = DFSearch(description=dfad)
        df = AID("df@Platform1", ["http://localhost:7778/acc"])
        content = Action(df, act)
        msg = ACLMessage(
            ACLPerformative.REQUEST,
            {
                "sender": self.local_aid,
                "receiver": {self.remote_df_aid},
                "protocol": "fipa-request",
                "ontology": "FIPA-Agent-Management",
                "language": "fipa-sl0",
                "content": str(content),
                "conversation-id": "test12345",
            },
        )

        return msg

    def decode_search_reply(self, content: str):
        """

        ((result
         (action
            (agent-identifier
                :name df@Platform1
                :addresses (sequence http://localhost:7778/acc))
         (search
            (df-agent-description
            :services
                (set
                (service-description
                    :name Ping
                    :type Test-Service)))
            (search-constraints
            :max-results -1))) (sequence)))
        """
        return content
