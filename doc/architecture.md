# Architecture

The goal is to create a fipa-to-xmpp bridge.

```ascii-art
   JADE Main     Bridge     XMPP server 
  ┌─────────┐   ┌───────┐   ┌────────┐  
  │         │───>       │───>        │  
  │         │   │       │   │        │  
  │         │   │       │   │        │  
  │         <───│       <───│        │  
  └─────────┘   └───────┘   └────────┘  
```

This implies to solve message transport issues, as well a
message formatting issues both for the message enveloppe 
(i.e. metadata) and content.

## Message transport

### FIPA-MTP connection

The simplest connexion protocol with JADE is the FIPA-specified
http/https MTP. In this protocol, both components use an http
server and an http client. Client send POST requests to send
messages to the peers. The post request includes both the message
enveloppe in XML format and a string representation of message,
in a mime-multipart body.

```ascii-art
  JADE MTP                                          Bridge  
─────────────────┐                          ┌───────────────
                 │                          │┌───────────┐  
                 │ http://localhost:7772/acc││Message    │  
                 │───────────────────────────>reception  │  
                 │                          ││& decoding │  
  Agent ID       │                          ││task       │  
  - nickname     │                          │└───────────┘  
  - platform     │         HTTP POST        │               
  - addresses    │                          │               
    (mtp url)    │                          │┌───────────┐  
                 │                          ││Message    │  
                 │                          ││formatting │  
                <───────────────────────────││& sending  │  
                 │ http://localhost:7778/acc││task       │  
                 │                          │└───────────┘  
─────────────────┘                          └───────────────
```

### XMPP server connexion

The XMPP server should be extended to be able

- to route all messages intended for Jade agents to the MTP bridge
- to receive messages from the bridge

The best architecture to do those functions is the
[Jabber Component Protocol](https://xmpp.org/extensions/xep-0114.html)
or XEP-0144.

```ascii-art
     Bridge                                    XMPP server  
────────────────┐                           ┌───────────────
 ┌─────────────┐│                           │ ┌───────────┐ 
 │slixmpp      ││                  TCP: 5347│ │ XEP-0144  │ 
 │             │┼───────────────────────────> │ plugin    │ 
 │ComponentXMPP│<──────────────────────────── │           │ 
 │             ││                           │ │           │ 
 │             ││                           │ │           │ 
 │             ││          XEP-0144         │ └───────────┘ 
 └─────────────┘│                           │               
                │                           │               
 subdomain:     │                           │  domain:      
 jade.localhost │                           │  localhost    
                │                           │               
                │                           │               
                │                           │               
────────────────┘                           └───────────────
```

Unfortunatelly, XEP-0144 is not implemented in pyjabber (with is default
xmpp server for spade). Basically, with XEP-0144, a server tcp socket is
opened by the plugin. When an external server component connects, it
identidied by a subdomain of the server's domain (e.g. jade.localhost, or
platform.localhost, where "platform" is the name of the FIPA agent platform)
authenticate using a shared secret. After that, the external component can
send messages to the server (coming from his subdomain), and can filter
messages addresses to his subdomain using the `feed` method.

Only the authentication is different from the usual client-server protocol.

### Internal Bridge Architecture


```ascii-art
 ┌────────────────────────────────────────────────────────┐ 
 │┌───────────────┐                      ┌───────────────┐│ 
 ││ aiohttp       │                      │ slixmpp       ││ 
 ││               │       incoming       │┌──────────┐   ││ 
 ││               │   ─────────┬─┬─┬─┐   ││          │   ││ 
 ██             ╶╶╶╶╶╶>        │ │ │ │╶╶╶╶> sender   │  ███ 
 ││               │   ─────────┴─┴─┴─┘   ││ task     │  ███ 
 ││               │                      ││          │   ││ 
 ││               │     async queues     │└──────────┘   ││ 
 ││               │     of ACLMessage    │               ││ 
 ││┌─────────────┐│                      │               ││ 
 │││             ││       outgoing       │               ││ 
 │││ sender      ││   ┌─┬─┬─┬─────────   │               ││ 
 ███ task        <╶╶╶╶│ │ │ │        <╶╶╶╶╶╶             ││ 
 │││             ││   └─┴─┴─┴─────────   │               ││ 
 ││└─────────────┘│                      │               ││ 
 │└───────────────┘                      └───────────────┘│ 
 └────────────────────────────────────────────────────────┘
```