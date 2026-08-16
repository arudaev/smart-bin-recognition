# The inference service. Build from the REPO ROOT, not from service/:
#
#     docker build -f service/Dockerfile -t sbr-detect .
#
# The context is the repo because the service genuinely needs three things from
# outside its own directory, and copying them is honest about that:
#
#   ml/src/sbr    the resolver. sbr.taxonomy is the reference implementation and
#                 is unit-tested; a second copy inside service/ would be the
#                 worst possible place for the rules about what may be thrown
#                 where to drift.
#   ml/configs    crop padding, min box size, the unknown threshold. Nothing that
#                 affects a run is hard-coded, here or in ml/.
#   data/taxonomy the streams, the form factors, the eleven named colours and the
#                 region packs - the product's spine.
#
# The layout under /app mirrors the repo on purpose. sbr.taxonomy resolves its
# data directory as `parents[3]/data/taxonomy` and sbr.config resolves configs as
# `parents[2]/configs`, so /app/ml/src/sbr/... finds /app/data and /app/ml/configs
# without either module needing to know it is in a container.

FROM python:3.11-slim

# Run as a non-root user with a writable home, which is what the Hugging Face
# hub cache wants and what a container should do anyway.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/ml/src:/app/service

WORKDIR /app

COPY --chown=user service/requirements.txt service/requirements.txt
RUN pip install --no-cache-dir --user -r service/requirements.txt

COPY --chown=user ml/src/sbr ml/src/sbr
COPY --chown=user ml/configs ml/configs
COPY --chown=user data/taxonomy data/taxonomy
COPY --chown=user service service

# Cloud Run injects PORT and it is not negotiable; 8080 is the local default.
EXPOSE 8080

# One worker, deliberately. The cost model is arithmetic about two vCPUs
# (docs/05 § 3), and two workers sharing them would make every latency number
# this service reports mean something other than "one frame on the tier we pay
# for". Concurrency is handled by the load shedder, not by more processes.
CMD ["sh", "-c", "uvicorn app:app --app-dir /app/service --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
