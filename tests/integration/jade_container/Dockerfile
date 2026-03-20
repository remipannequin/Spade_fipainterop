FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /build
COPY PingAgent.java .
COPY pom.xml .

#RUN mvn dependency:get -Dartifact=com.gitlab.jade-project:jade:master-SNAPSHOT
RUN mvn dependency:copy-dependencies -DincludeScope=runtime
RUN javac -cp "target/dependency/*" PingAgent.java

FROM eclipse-temurin:21-jdk

WORKDIR /app

COPY --from=build /build/target/dependency/*.jar libs/
COPY --from=build /build/*.class .


EXPOSE 1099 7778

ENV LOCAL_AGENT_NAME=ping1
ENV REMOTE_AGENT_NAME=ping2@Platform2
ENV REMOTE_URL=http://localhost:7772/acc
ENV MODE=recv

CMD java \
    --add-exports java.xml/com.sun.org.apache.xerces.internal.jaxp=ALL-UNNAMED \
    --add-opens java.xml/com.sun.org.apache.xerces.internal.jaxp=ALL-UNNAMED\
    -cp .:./libs/*\
    jade.Boot\
    -name Platform1\
    -mtps "jade.mtp.http.MessageTransportProtocol(http://localhost:7778/acc)"\
    "${LOCAL_AGENT_NAME}:PingAgent(${REMOTE_AGENT_NAME},${REMOTE_URL},${MODE}})"