./launch_jade.sh 1 da1:jade.tools.DummyAgent.DummyAgent &
PID1=$!
trap "echo 'Terminating platform 1'; kill $PID1; exit" SIGINT SIGTERM

./launch_jade.sh 2 da2:jade.tools.DummyAgent.DummyAgent
EXIT2=$?

if kill -0 $PID1 2>/dev/null; then
    echo "Killing remaining process with PID $PID1"
    kill $PID1
fi

wait $PID1

exit $EXIT2
