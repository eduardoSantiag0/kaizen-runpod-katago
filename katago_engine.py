import json
import select
import subprocess
import threading

# Deadline for a single KataGo response line. stdout.readline() blocks
# forever with no timeout of its own, so a hung-but-alive KataGo process
# (poll() still None, no crash) would otherwise wedge this request — and
# every later one too, since they all share the same process behind LOCK.
KATAGO_RESPONSE_TIMEOUT_SECONDS = 60


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


def readLineWithTimeout(process, timeout_seconds):
    ready, _, _ = select.select([process.stdout], [], [], timeout_seconds)
    if not ready:
        return None
    return process.stdout.readline()


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
        line = readLineWithTimeout(KATAGO_PROCESS, KATAGO_RESPONSE_TIMEOUT_SECONDS)

        if line is None:
            # KataGo está vivo (poll() não detecta isso) mas não respondeu
            # dentro do prazo — mata e reinicia explicitamente, em vez de
            # travar essa e toda requisição futura (compartilham o LOCK).
            KATAGO_PROCESS.kill()
            KATAGO_PROCESS.wait()
            KATAGO_PROCESS = startKatagoProcess()
            raise RuntimeError("KataGo não respondeu a tempo; processo reiniciado")

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
