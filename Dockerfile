FROM python:3.11-slim as builder


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1


RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*


RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"


COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt


FROM python:3.11-slim


RUN apt-get update && apt-get install -y \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*


RUN groupadd -r webnotes && useradd -r -g webnotes webnotes


COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"


WORKDIR /app

COPY . .

RUN chown -R webnotes:webnotes /app

USER webnotes

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.connect(('localhost',8000))" || exit 1


CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
