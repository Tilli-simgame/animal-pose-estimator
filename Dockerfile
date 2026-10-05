# Production image: CPU-only PyTorch, model weights baked in, runs as a non-root user.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.16 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_SYNC=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    HORSE_DATA_DIR=/data \
    COOKIE_SECURE=1

# OpenCV (pulled in by DeepLabCut) needs glib; PyTorch needs OpenMP
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so code changes do not reinstall them
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

# Download the SuperAnimal weights at build time, not on first start. The download is
# owner-only (0400), so make it readable for the non-root user that runs the app.
RUN uv run python -c "\
from deeplabcut.pose_estimation_pytorch import modelzoo; \
[modelzoo.get_super_animal_snapshot_path(dataset='superanimal_quadruped', model_name=m) \
 for m in ('hrnet_w32', 'fasterrcnn_resnet50_fpn_v2')]" \
    && chmod -R a+rX /app/.venv/lib/python3.12/site-packages/deeplabcut/modelzoo/checkpoints

RUN useradd --uid 1000 --create-home app && mkdir -p /data && chown app:app /data
USER app
VOLUME /data
EXPOSE 8000

# One worker: the model takes ~2 GB of memory and requests are short
CMD ["uv", "run", "uvicorn", "horse_conformation.app:app", \
     "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
