import json
import subprocess
import runpod

katago = subprocess.Popen(
    [
        "katago",
        "analysis",
        "-config", "/app/config/analysis.cfg",
        "-model", "/app/models/model.bin.gz"
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    bufsize=1
)


def handler(event):
    request = event["input"]

    katago.stdin.write(json.dumps(request) + "\n")
    katago.stdin.flush()

    response = katago.stdout.readline()

    return json.loads(response)


runpod.serverless.start({
    "handler": handler
})