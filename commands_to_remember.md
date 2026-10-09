
Run Katago locally

    `docker run -it --rm `
    --gpus all `
    --name kaizen-katago `
    --entrypoint katago `
    meukatago `
    analysis `
    -config /app/config/analysis.cfg `
    -model /app/models/model.bin.gz`

Testar com endpoint

    docker run -it --rm `
    --gpus all `
    --name kaizen-katago `
    -p 8970:8000 `
    meukatago `
    python3 -u handler.py --rp_serve_api --rp_api_port 8000

