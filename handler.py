import json
import subprocess
import threading
import runpod

katago = subprocess.Popen(
    [
        "katago",
        "analysis",

        "-config",
        "/app/config/analysis.cfg",

        "-model",
        "/app/models/strong.bin.gz",

        "-human-model",
        "/app/models/human.bin.gz",
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    bufsize=1,
)
lock = threading.Lock()


def handler(event):
    request = event["input"]
    request.setdefault("id", "q")

    with lock:
        if katago.poll() is not None:
            return {"error": "KataGo process has exited"}

        katago.stdin.write(json.dumps(request) + "\n")
        katago.stdin.flush()

        # Um pedido pode gerar várias respostas (um por turno analisado).
        # Se usar reportDuringSearchEvery, filtre também as parciais (isDuringSearch).
        expected = len(request.get("analyzeTurns", [None]))
        results = []
        while len(results) < expected:
            line = katago.stdout.readline()
            if not line:
                return {"error": "KataGo closed stdout"}
            resp = json.loads(line)
            if "error" in resp:
                return resp
            if resp.get("id") != request["id"]:
                continue  # sobra de pedido anterior
            if resp.get("isDuringSearch"):
                continue
            results.append(resp)

    return results[0] if expected == 1 else results


runpod.serverless.start({"handler": handler})