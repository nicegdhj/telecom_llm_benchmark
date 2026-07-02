# ── 后端服务镜像（FastAPI + Worker）─────────────────────────────────
# 注意：此容器通过 docker socket 启动 ais_bench 计算容器
#       ais_bench 本身有独立的 Dockerfile（deploy_docker/ais_bench/Dockerfile）
FROM python:3.10-slim

WORKDIR /app

# ── 安装 docker CLI（后端通过 `docker run` 启动 ais_bench）──────
ARG DOCKER_VERSION=27.0.3
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in \
         amd64) DOCKER_ARCH=x86_64 ;; \
         arm64) DOCKER_ARCH=aarch64 ;; \
         *)     DOCKER_ARCH=$ARCH ;; \
       esac \
    && curl -fsSL --retry 3 "https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-${DOCKER_VERSION}.tgz" \
       | tar xz --strip-components=1 -C /usr/local/bin docker/docker \
    && rm -rf /var/lib/apt/lists/*

# ── 安装 Python 依赖 ───────────────────────────────────────────────
COPY backend/pyproject.toml ./backend/
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] sqlalchemy pydantic pydantic-settings pyyaml python-multipart openpyxl tokenizers

# ── 复制后端源码 ───────────────────────────────────────────────────
COPY backend/app ./backend/app

ENV PYTHONPATH=/app
ENV EVAL_BACKEND_WORKSPACE_DIR=/opt/eval_workspace
ENV EVAL_BACKEND_BACKEND_DATA_DIR=/opt/eval_backend_data
ENV EVAL_BACKEND_CODE_DIR=/opt/eval_workspace/code
ENV EVAL_BACKEND_DOCKER_IMAGE_TAG=benchmark-eval:latest
ENV EVAL_BACKEND_DEFAULT_JOB_CONCURRENCY=4

EXPOSE 8080

WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
