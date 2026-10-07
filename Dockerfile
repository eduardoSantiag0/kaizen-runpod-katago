# =========================
# 1. Build KataGo
# =========================
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04 AS builder

ARG KATAGO_VERSION=v1.18.2

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    cmake \
    build-essential \
    zlib1g-dev \
    libzip-dev \
    libboost-filesystem-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN git clone \
    --depth 1 \
    --branch ${KATAGO_VERSION} \
    https://github.com/lightvector/KataGo.git

WORKDIR /build/KataGo/cpp

RUN cmake . \
    -DUSE_BACKEND=CUDA \
    -DCMAKE_BUILD_TYPE=Release \
    -DNO_GIT_REVISION=1 \
    && make -j"$(nproc)"


# =========================
# 2. Runtime
# =========================
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-venv \
    libboost-filesystem-dev \
    libzip-dev \
    zlib1g \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# RunPod SDK isolado
RUN python3 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir runpod

ENV PATH="/venv/bin:$PATH"

WORKDIR /app

# KataGo
COPY --from=builder \
    /build/KataGo/cpp/katago \
    /usr/local/bin/katago

# Worker RunPod
COPY handler.py .

# Config ficam dentro da imagem
COPY config/analysis.cfg ./config/analysis.cfg

# b18c384nbt-humanv0.bin.gz
COPY models/model.bin.gz ./models/model.bin.gz 

CMD ["python3", "-u", "handler.py"]

# docker build -t kaizen-katago-worker .

# ./katago gtp -config gtp_human5k_example.cfg -model your_favorite_normal_model_for_katago.bin.gz -human-model b18c384nbt-humanv0.bin.gz

# docker run --rm -it `
#   --gpus all `
#   --mount type=bind,source="$($PWD.Path)\test_input.json",target=/app/test_input.json,readonly `
#   meukatago