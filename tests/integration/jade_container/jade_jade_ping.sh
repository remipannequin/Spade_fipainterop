./launch_jade.sh 1 "ping1:fr.univlorraine.cran.c2ps.PingAgent(ping2@Platform2,http://localhost:7772/JADE)" &
PID1=$!
trap "echo 'Terminating platform 1'; kill $PID1; exit" SIGINT SIGTERM

./launch_jade.sh 2 "ping2:fr.univlorraine.cran.c2ps.PingAgent(ping1@Platform1,http://localhost:7771/JADE)"
EXIT2=$?

if kill -0 $PID1 2>/dev/null; then
    echo "Killing remaining process with PID $PID1"
    kill $PID1
fi

wait $PID1

exit $EXIT2
