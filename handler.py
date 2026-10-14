
import json
import logging
import os
import subprocess
import threading
import urllib.error
import urllib.request
import uuid

import runpod

from events import AnalysisCreatedEvent

CALLBACK_URL = os.environ.get("KAIZAN_CALLBACK_URL", "http://host.docker.internal:8080/kaizan/api/v1/katago")

KATAGO_PROCESS = subprocess.Popen(
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

LOCK = threading.Lock()

def setupLogger(log_level=logging.DEBUG):

    log_format = logging.Formatter(
        '%(asctime)s - %(levelname)s - [Request: %(request_id)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    log = logging.getLogger("runpod_worker")
    log.setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)

    if not log.handlers:
        log.addHandler(console_handler)

    return log

LOG = setupLogger(log_level=logging.DEBUG)
LOG = logging.LoggerAdapter(LOG, {"request_id": "N/A"})

LOG.info("Logger initialized. Ready to process jobs.")

def sendRunPodResponse(runpod_response, job_logger):
    body = json.dumps(runpod_response).encode("utf-8")

    request = urllib.request.Request(
        CALLBACK_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        urllib.request.urlopen(request, timeout=10)
        job_logger.info("Callback enviado para %s", CALLBACK_URL)
    except urllib.error.URLError as error:
        job_logger.error("Falha ao enviar callback para %s: %s", CALLBACK_URL, error, exc_info=True)


def sendRunPodResponseAsync(runpod_response, job_logger):
    thread = threading.Thread(target=sendRunPodResponse, args=(runpod_response, job_logger), daemon=True)
    thread.start()


def queryKatago(query):
    payload = query.toQueryDict()

    if "analyzeTurns" in payload:
        expected = len(payload["analyzeTurns"])
    else:
        expected = 1

    if expected == 0:
        return []

    if KATAGO_PROCESS.poll() != None:
        raise RuntimeError("KataGo encerrou")

    KATAGO_PROCESS.stdin.write(json.dumps(payload) + "\n")
    KATAGO_PROCESS.stdin.flush()

    results = {}

    while len(results) < expected:
        line = KATAGO_PROCESS.stdout.readline()

        if line == "":
            raise RuntimeError("KataGo fechou stdout")

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


def firstRun(katago_query):
    LOG.info("Iniciando a primeira run: %s", katago_query)
    total_moves = len(katago_query.moves)

    analyze_turns = []
    turn_number = 0
    while turn_number <= total_moves:
        analyze_turns.append(turn_number)
        turn_number = turn_number + 1

    full_query = katago_query.toBuilder().analyzeTurns(analyze_turns).maxVisits(20).build()

    return queryKatago(full_query)


def findCriticalPoints(katago_query, analyses):
    moves = katago_query.moves
    total_moves = len(moves)

    by_turn = {}
    for analysis in analyses:
        by_turn[analysis["turnNumber"]] = analysis

    critical_points = []
    phase_names = ["opening", "middlegame", "endgame"]

    phase_index = 0
    while phase_index < 3:
        # Divide o número de jogadas em 3 partes.
        start_turn = (phase_index * total_moves) // 3 + 1
        end_turn = ((phase_index + 1) * total_moves) // 3

        worst_point = None

        turn_number = start_turn
        while turn_number <= end_turn:
            winrate_before = by_turn[turn_number - 1]["rootInfo"]["winrate"]
            winrate_after = by_turn[turn_number]["rootInfo"]["winrate"]

            move_entry = moves[turn_number - 1]
            player = move_entry[0]
            move = move_entry[1]

            if player == "B":
                winrate_drop = winrate_before - winrate_after
            else:
                winrate_drop = winrate_after - winrate_before

            if worst_point == None:
                worst_point = {
                    "phase": phase_names[phase_index],
                    "turn": turn_number,
                    "player": player,
                    "move": move,
                    "winrateDrop": winrate_drop,
                }
            elif winrate_drop > worst_point["winrateDrop"]:
                worst_point = {
                    "phase": phase_names[phase_index],
                    "turn": turn_number,
                    "player": player,
                    "move": move,
                    "winrateDrop": winrate_drop,
                }

            turn_number = turn_number + 1

        if worst_point != None:
            critical_points.append(worst_point)

        phase_index = phase_index + 1

    return critical_points


def analyzeCriticalPoints(katago_query, critical_points):
    turns = []

    for point in critical_points:
        turn_number = point["turn"]
        turns.append(turn_number - 1)
        turns.append(turn_number)

    unique_turns = []
    for turn_number in turns:
        if turn_number not in unique_turns:
            unique_turns.append(turn_number)
    unique_turns.sort()

    detail_query = katago_query.toBuilder().analyzeTurns(unique_turns).maxVisits(200).build()

    analyses = queryKatago(detail_query)

    by_turn = {}
    for analysis in analyses:
        by_turn[analysis["turnNumber"]] = analysis

    results = []

    for point in critical_points:
        turn_number = point["turn"]

        result_item = {}
        result_item["phase"] = point["phase"]
        result_item["turn"] = point["turn"]
        result_item["player"] = point["player"]
        result_item["move"] = point["move"]
        result_item["winrateDrop"] = point["winrateDrop"]
        result_item["before"] = by_turn[turn_number - 1]
        result_item["after"] = by_turn[turn_number]

        results.append(result_item)

    return results


async def handler(event):
    try:
        analysis_event = AnalysisCreatedEvent.fromDict(event["input"])
    except (KeyError, TypeError) as error:
        return {"error": "Payload inválido: " + str(error)}

    katago_query = analysis_event.katagoQuery
    analysis_dto = analysis_event.analysisDTO

    if katago_query.id != None and katago_query.id != "":
        request_id = katago_query.id
    else:
        request_id = str(uuid.uuid4())

    job_logger = logging.LoggerAdapter(LOG.logger, {"request_id": request_id})

    if len(katago_query.moves) == 0:
        job_logger.warning("Requisição recebida sem jogadas.")
        return {"error": "Partida sem jogadas"}
    job_logger.info("Iniciando análise: %s", katago_query)

    job_logger.info("Iniciando análise de %d jogadas.", len(katago_query.moves))

    LOCK.acquire()
    try:
        analyses = firstRun(katago_query)

        critical_points = findCriticalPoints(katago_query, analyses)

        results = analyzeCriticalPoints(katago_query, critical_points)

        job_logger.info("Análise concluída com %d pontos críticos.", len(results))

        runpod_response = {
            "id": katago_query.id,
            "output": {
                "chatId": analysis_dto.chatId,
                "correlationId": analysis_dto.correlationId,
                "status": "COMPLETED",
                "output": {
                    "gameId": analysis_dto.correlationId,
                    "totalMoves": len(katago_query.moves),
                    "criticalPoints": results,
                },
            },
        }

        sendRunPodResponseAsync(runpod_response, job_logger)

        return runpod_response

    except Exception as error:
        job_logger.error("Falha ao processar análise: %s", error, exc_info=True)

        runpod_response = {
            "id": katago_query.id,
            "output": {
                "chatId": analysis_dto.chatId,
                "correlationId": analysis_dto.correlationId,
                "status": "FAILED",
                "output": None,
            },
        }

        sendRunPodResponseAsync(runpod_response, job_logger)

        return {"error": str(error)}

    finally:
        LOCK.release()


runpod.serverless.start({"handler": handler})
