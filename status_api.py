import logging
import os

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY")
RUNPOD_ENDPOINT_ID = os.environ.get("RUNPOD_ENDPOINT_ID")
RUNPOD_API_BASE_URL = os.environ.get("RUNPOD_API_BASE_URL", "https://api.runpod.ai/v2")

# Para testar contra o container local (handler.py rodando com --rp_serve_api,
# ex: http://localhost:8970): o servidor local expõe as rotas sem o prefixo
# /v2/{endpoint_id} e sem exigir API key.
RUNPOD_LOCAL_URL = os.environ.get("RUNPOD_LOCAL_URL")

# http://host.docker.internal:8080/kaizan/api/v1/katago

LOG = logging.getLogger("status_api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Kaizan RunPod Status API")


class CancelRequest(BaseModel):
    correlationId: str


def runpodHeaders():
    if RUNPOD_LOCAL_URL:
        return {}

    if not RUNPOD_API_KEY:
        raise HTTPException(status_code=500, detail="RUNPOD_API_KEY não configurada")

    return {"Authorization": f"Bearer {RUNPOD_API_KEY}"}


async def callRunpod(http_method: str, url: str, not_found_detail: str):
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.request(http_method, url, headers=runpodHeaders())
        except httpx.RequestError as error:
            LOG.error("Falha ao chamar RunPod (%s %s): %s", http_method, url, error)
            raise HTTPException(status_code=502, detail="Falha ao contatar o RunPod") from error

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=not_found_detail)

    if response.is_error:
        LOG.error(
            "RunPod retornou erro (%s %s): HTTP %s - %s",
            http_method, url, response.status_code, response.text,
        )
        raise HTTPException(status_code=502, detail="RunPod retornou erro")

    return response.json()


def runpodEndpointUrl(*parts: str) -> str:
    if RUNPOD_LOCAL_URL:
        return "/".join([RUNPOD_LOCAL_URL.rstrip("/"), *parts])

    if not RUNPOD_ENDPOINT_ID:
        raise HTTPException(status_code=500, detail="RUNPOD_ENDPOINT_ID não configurada")

    return "/".join([f"{RUNPOD_API_BASE_URL}/{RUNPOD_ENDPOINT_ID}", *parts])


@app.get("/status")
async def getStatus(correlationId: str):
    url = runpodEndpointUrl("status", correlationId)

    # O servidor local de teste (--rp_serve_api) só aceita POST em /status/{id}
    # e já roda o job na hora; na nuvem o endpoint real é GET.
    http_method = "POST" if RUNPOD_LOCAL_URL else "GET"

    return await callRunpod(http_method, url, "Job não encontrado")


@app.post("/cancel")
async def cancelJob(request: CancelRequest):
    if RUNPOD_LOCAL_URL:
        raise HTTPException(
            status_code=501,
            detail="O servidor local (--rp_serve_api) não tem endpoint /cancel; teste contra a nuvem do RunPod",
        )

    url = runpodEndpointUrl("cancel", request.correlationId)
    return await callRunpod("POST", url, "Job não encontrado")


@app.get("/health")
async def getHealth():
    if RUNPOD_LOCAL_URL:
        raise HTTPException(
            status_code=501,
            detail="O servidor local (--rp_serve_api) não tem endpoint /health; teste contra a nuvem do RunPod",
        )

    url = runpodEndpointUrl("health")
    return await callRunpod("GET", url, "Endpoint não encontrado")
