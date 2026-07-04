# Shabd web — Hugging Face Spaces (Docker Space, free CPU tier).
# Spec: specs/song-transcriber-web.md
FROM python:3.10-slim

RUN useradd -m -u 1000 user
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shabd/ shabd/
COPY templates/ templates/

USER user
# Model files download once at startup into the user cache (ephemeral disk —
# re-downloaded after a restart, which is fine and fast inside HF's network).
ENV HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    PORT=7860 \
    SHABD_WEB_WARMUP=1

EXPOSE 7860
CMD ["python", "-m", "shabd.web"]
