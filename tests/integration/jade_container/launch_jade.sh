# Get first argument: should be an int
PLATFORM=${1:-1}
mvn clean compile
mvn dependency:copy-dependencies
export JAVA_HOME=/usr/lib/jvm/java-21
export LD_LIBRARY_PATH=$JAVA_HOME/lib/server:$LD_LIBRARY_PATH
# Set X11 display
export DISPLAY=:0
mkdir -p pf${PLATFORM}
cd pf${PLATFORM}
$JAVA_HOME/bin/java \
  -Djava.awt.headless=false \
  --add-modules java.desktop \
  --add-exports java.xml/com.sun.org.apache.xerces.internal.jaxp=ALL-UNNAMED \
  --add-opens java.xml/com.sun.org.apache.xerces.internal.jaxp=ALL-UNNAMED \
  -cp "../target/classes:../target/dependency/*" \
  jade.Boot \
  -gui \
  -name Platform${PLATFORM} \
  -port 10${PLATFORM}99 \
  -mtps "jade.mtp.http.MessageTransportProtocol(http://localhost:777${PLATFORM}/JADE)" \
  ${@:2}
cd ..