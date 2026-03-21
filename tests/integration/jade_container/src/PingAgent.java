import jade.core.AID;
import jade.core.Agent;
import jade.core.behaviours.CyclicBehaviour;
import jade.core.behaviours.OneShotBehaviour;
import jade.core.behaviours.ReceiverBehaviour;
import jade.core.behaviours.SequentialBehaviour;
import jade.core.behaviours.TickerBehaviour;
import jade.core.behaviours.WakerBehaviour;
import jade.lang.acl.ACLMessage;
import jade.lang.acl.MessageTemplate;
import java.util.Date;
import jade.domain.DFService;
import jade.domain.FIPAException;
import jade.domain.FIPAAgentManagement.DFAgentDescription;
import jade.domain.FIPAAgentManagement.ServiceDescription;

/**
 * An agent that periodically sends "ping" messages to a peer and waits for 
 * "pong" responses.
 * It also listens for incoming "ping" messages and responds with "pong".
 * 
 * Arguments:
 * - required: peer name (AID)
 * - optional: peer address (URL)
 * - optional: mode ("send", "recv") if not specified, the agent will both send and receive pings
 */
public class PingAgent extends jade.core.Agent {
   
    private final class PingResponder extends CyclicBehaviour {
        public void action() {
            MessageTemplate mt = MessageTemplate.and(MessageTemplate.MatchProtocol("c2ps-ping"),
                                                     MessageTemplate.MatchPerformative(ACLMessage.REQUEST));
            
            ACLMessage msg = myAgent.receive(mt);
            if (msg != null) {
                System.out.printf("%s - got a ping request from %s\n", myAgent.getAID().getName(), msg.getSender().getName());
                ACLMessage response = msg.createReply();
                response.setPerformative(ACLMessage.INFORM);
                response.setContent("pong");
                send(response);
            } else {
                block();
            }
        }
    }

    private final class ProcPingReply extends OneShotBehaviour {
        private final ReceiverBehaviour rb;
        private final int num;

        private ProcPingReply(ReceiverBehaviour rb, int ping_num) {
            this.rb = rb;
            this.num = ping_num;
        }

        public void action() {
            try {
                ACLMessage response = rb.getMessage();
                System.out.printf("%s - received response for ping %d from %s\n", myAgent.getAID().getName(), num, response.getSender().getName());
            } catch (ReceiverBehaviour.TimedOut e) {
                System.out.printf("%s - no response received for ping %d from %s\n", myAgent.getAID().getName(), num, peer.getName());
            } catch (ReceiverBehaviour.NotYetReady e) {
                System.out.printf("%s - receiver not ready for ping %d\n", myAgent.getAID().getName(), num);
            }
        }
    }   


    private final class TickerPingSenderBehaviour extends TickerBehaviour {
        
        private TickerPingSenderBehaviour(Agent a, long period) {
            super(a, period);
        }

        public void onTick() {
            // prepare the ping message
            ACLMessage ping = new ACLMessage(ACLMessage.REQUEST);
            int timestamp = (int)(System.currentTimeMillis() / 1000);
            String conv_id = String.format("%s_%d_%d", getAID().getName(), num, timestamp);
            ping.addReceiver(peer);
            ping.setProtocol("c2ps-ping");
            ping.setContent(String.format("ping_%d", num));
            ping.setConversationId(conv_id);
            Date timeout = new Date(System.currentTimeMillis() + 3000);
            ping.setReplyByDate(timeout);
            // Set up a receiver behaviour to wait for the response to this ping
            MessageTemplate mt = MessageTemplate.and(
                MessageTemplate.MatchConversationId(conv_id),
                MessageTemplate.MatchPerformative(ACLMessage.INFORM)
            );
            SequentialBehaviour sb = new SequentialBehaviour();
            ReceiverBehaviour rb = new ReceiverBehaviour(myAgent, 3000, mt);
            sb.addSubBehaviour(rb);
            OneShotBehaviour proc_response = new ProcPingReply(rb, num);
            sb.addSubBehaviour(proc_response);
            addBehaviour(sb);
            // Send the ping message
            System.out.printf("%s - sending ping (%d) to: %s\n", myAgent.getAID().getName(), num, peer.getName());
            send(ping);
            num++;
        }
    }


    private int num = 0;
    private AID peer;


    public void setup() {
        // Get arguments
        Object[] args = getArguments();
        if (args == null || args.length < 1) {
            System.out.println("Usage: PingAgent(<peer_name>,[peer_addr],[send|recv])");
            doDelete();
            return;
        }
        String peer_name = (String)args[0];
        peer = new AID(peer_name, peer_name.contains("@"));
        if (args.length >= 2) {
            String peer_addr = (String)args[1];
            peer.addAddresses(peer_addr);
        }
        boolean send = true;
        boolean recv = true;
        if (args.length >= 3) {
            String mode = (String)args[2];
            if (mode.equalsIgnoreCase("recv")) {
                send = false;
                recv = true;
            } else if (mode.equalsIgnoreCase("send")) {
                send = true;
                recv = false;
            } 
        }
        // Register a service in the DF (to test querying the DF from outside)
        DFAgentDescription dfd = new DFAgentDescription();
        dfd.setName(getAID());
        // Create service description
        ServiceDescription sd = new ServiceDescription();
        sd.setType("Test-Service");
        sd.setName("Ping");
        // Add service to agent description
        dfd.addServices(sd);

        try {
            // Register to DF
            DFService.register(this, dfd);
        } catch (FIPAException e) {
            e.printStackTrace();
        }

        // Periodically send ping messages to the peer
        if (send) {
            int randomDelay = (int)(Math.random() * 5000);
            addBehaviour(new WakerBehaviour(this, randomDelay) {
                protected void onWake() {
                    addBehaviour(new TickerPingSenderBehaviour(myAgent, 5000));
                }
            });
        }
        // Listen for incoming ping messages and respond with pong
        if (recv) {
            addBehaviour(new PingResponder());
        }
        //jade.mtp.http.HTTPServer
    }
}