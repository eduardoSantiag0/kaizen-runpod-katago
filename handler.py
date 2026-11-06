
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
import uuid

import runpod

from events import AnalysisCreatedEvent
from katago_engine import LOCK, queryKatago

CALLBACK_URL = os.environ.get("KAIZAN_CALLBACK_URL", "http://host.docker.internal:8080/kaizan/api/v1/katago")
CALLBACK_MAX_ATTEMPTS = 3
CALLBACK_RETRY_BACKOFF_SECONDS = 2
RUNPOD_HEADER_SECRET = os.environ.get("RUNPOD_HEADER_SECRET")

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

    headers = {"Content-Type": "application/json"}
    if RUNPOD_HEADER_SECRET:
        headers["X-Kaizen-Secret"] = RUNPOD_HEADER_SECRET

    attempt = 1
    while attempt <= CALLBACK_MAX_ATTEMPTS:
        request = urllib.request.Request(
            CALLBACK_URL,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            urllib.request.urlopen(request, timeout=10)
            job_logger.info("Callback enviado para %s (tentativa %d)", CALLBACK_URL, attempt)
            return
        except urllib.error.HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")

            if error.code < 500:
                job_logger.error(
                    "Falha ao enviar callback para %s: HTTP %s - %s\nCorpo enviado: %s\nCorpo da resposta: %s",
                    CALLBACK_URL, error.code, error.reason, body.decode("utf-8"), error_body,
                )
                return

            job_logger.warning(
                "Tentativa %d/%d falhou ao enviar callback para %s: HTTP %s - %s\nCorpo da resposta: %s",
                attempt, CALLBACK_MAX_ATTEMPTS, CALLBACK_URL, error.code, error.reason, error_body,
            )
        except (urllib.error.URLError, TimeoutError) as error:
            job_logger.warning(
                "Tentativa %d/%d falhou ao enviar callback para %s: %s",
                attempt, CALLBACK_MAX_ATTEMPTS, CALLBACK_URL, error,
            )

        if attempt == CALLBACK_MAX_ATTEMPTS:
            job_logger.error(
                "Falha ao enviar callback para %s apos %d tentativas. Corpo enviado: %s",
                CALLBACK_URL, CALLBACK_MAX_ATTEMPTS, body.decode("utf-8"),
            )
            return

        time.sleep(CALLBACK_RETRY_BACKOFF_SECONDS * attempt)
        attempt = attempt + 1


def sendRunPodResponseAsync(runpod_response, job_logger):
    thread = threading.Thread(target=sendRunPodResponse, args=(runpod_response, job_logger), daemon=True)
    thread.start()


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


# docker compose up
