
import json
import subprocess
import threading
import uuid

import runpod

katago = subprocess.Popen(
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

lock = threading.Lock()

def query_katago(request):
    query = request.copy()
    query["id"] = request.id

    query.pop("reportDuringSearchEvery", None)

    turns = query.get("analyzeTurns")
    expected = len(turns) if turns is not None else 1

    if expected == 0:
        return []

    if katago.poll() is not None:
        raise RuntimeError("KataGo encerrou")

    katago.stdin.write(json.dumps(query) + "\n")
    katago.stdin.flush()

    results = {}

    while len(results) < expected:
        line = katago.stdout.readline()

        if not line:
            raise RuntimeError("KataGo fechou stdout")

        response = json.loads(line)

        # Ignora respostas de outras consultas.
        if response.get("id") != query["id"]:
            continue

        if "error" in response:
            raise RuntimeError(str(response["error"]))

        if "warning" in response:
            continue

        if response.get("isDuringSearch"):
            continue

        turn = response["turnNumber"]
        results[turn] = response

    # Análises ordenadas por turno.
    return [results[t] for t in sorted(results)]


def first_run(request):
    query = request.copy()

    total_moves = len(query["moves"])
    query["analyzeTurns"] = list(range(total_moves + 1))

    query["maxVisits"] = 100

    return query_katago(query)


def find_critical_points(request, analyses):
    moves = request["moves"]
    total = len(moves)

    # Permite buscar uma análise pelo turno.
    by_turn = {
        item["turnNumber"]: item
        for item in analyses
    }

    critical = []
    phases = ["opening", "middlegame", "endgame"]

    for phase in range(3):
        # Divide o número de jogadas em 3 partes.
        start = (phase * total) // 3 + 1
        end = ((phase + 1) * total) // 3

        worst = None

        for turn in range(start, end + 1):
            before = by_turn[turn - 1]["rootInfo"]["winrate"]
            after = by_turn[turn]["rootInfo"]["winrate"]

            player, move = moves[turn - 1]

            if player == "B":
                drop = before - after
            else:
                drop = after - before

            if worst is None or drop > worst["winrateDrop"]:
                worst = {
                    "phase": phases[phase],
                    "turn": turn,
                    "player": player,
                    "move": move,
                    "winrateDrop": drop,
                }

        if worst is not None:
            critical.append(worst)

    return critical


def analyze_critical_points(request, critical):
    query = request.copy()

    turns = []

    for point in critical:
        turn = point["turn"]
        turns.extend([turn - 1, turn])

    query["analyzeTurns"] = sorted(set(turns))

    query["maxVisits"] = 1000

    analyses = query_katago(query)

    by_turn = {
        item["turnNumber"]: item
        for item in analyses
    }

    results = []

    for point in critical:
        turn = point["turn"]

        results.append({
            **point,
            "before": by_turn[turn - 1],
            "after": by_turn[turn],
        })

    return results


def handler(event):
    request = event["input"]

    if not request.get("moves"):
        return {"error": "Partida sem jogadas"}

    with lock:
        try:
            analyses = first_run(request)

            critical = find_critical_points(request, analyses)

            results = analyze_critical_points(request, critical)

            return {
                "gameId": request.get("id"),
                "totalMoves": len(request["moves"]),
                "criticalPoints": results,
            }

        except Exception as error:
            return {"error": str(error)}


runpod.serverless.start({"handler": handler})
