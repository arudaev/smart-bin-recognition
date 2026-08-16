# Hugging Face Space, Docker SDK, CPU-basic (2 vCPU / 16 GB) – the free tier the
# cost model is built on. Nothing here may need a paid upgrade to run.
FROM python:3.11-slim

# HF Spaces run as uid 1000 and expect a writable home for the hub cache.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONUNBUFFERED=1

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user app.py .

EXPOSE 7860

# One worker on purpose. Two would share the two vCPUs and the number this
# Space exists to produce would stop meaning "one frame on the free tier".
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
