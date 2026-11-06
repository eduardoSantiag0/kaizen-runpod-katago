import json
import subprocess
import threading


def startKatagoProcess():
    return subprocess.Popen(
        [
            "katago",
            "analysis",
            "-config", "/app/config/analysis.cfg",
            "-model", "/app/models/strong.bin.gz",
            "-human-model", "/app/models/human.bin.gz",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


KATAGO_PROCESS = startKatagoProcess()

LOCK = threading.Lock()


def queryKatago(query):
    global KATAGO_PROCESS

    payload = query.toQueryDict()

    if "analyzeTurns" in payload:
        expected = len(payload["analyzeTurns"])
    else:
        expected = 1

    if expected == 0:
        return []

    if KATAGO_PROCESS.poll() != None:
        # O processo morreu em uma requisição anterior: reinicia para que o
        # worker continue aceitando e processando novas requisições.
        KATAGO_PROCESS = startKatagoProcess()
        raise RuntimeError("KataGo encerrou; processo reiniciado")

    KATAGO_PROCESS.stdin.write(json.dumps(payload) + "\n")
    KATAGO_PROCESS.stdin.flush()

    results = {}

    while len(results) < expected:
        line = KATAGO_PROCESS.stdout.readline()

        if line == "":
            # stdout fechado (processo morreu durante esta requisição):
            # reinicia para que futuras requisições continuem sendo atendidas.
            KATAGO_PROCESS = startKatagoProcess()
            raise RuntimeError("KataGo fechou stdout; processo reiniciado")

        response = json.loads(line)

        # Ignora respostas de outras consultas.
        if response.get("id") != query.id:
            continue

        if "error" in response:
            raise RuntimeError(str(response["error"]))

        if "warning" in response:
            continue

        if response.get("isDuringSearch"):
            continue

        turn_number = response["turnNumber"]
        results[turn_number] = response

    # Análises ordenadas por turno.
    ordered_turns = []
    for turn_number in results:
        ordered_turns.append(turn_number)
    ordered_turns.sort()

    ordered_results = []
    for turn_number in ordered_turns:
        ordered_results.append(results[turn_number])

    return ordered_results
