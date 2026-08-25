# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/huggingface \
    TRANSFORMERS_CACHE=/opt/huggingface/transformers

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && mkdir -p /app/data /app/logs /opt/huggingface \
    && chown -R app:app /app /opt/huggingface

FROM base AS worker

COPY requirements.txt ./
# Keep local test tooling out of the runtime image.
RUN python -m pip install --upgrade pip \
    && python -m pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && grep -Ev '^(pytest|pytest-cov|testcontainers\[postgres\])[[:space:]]*$' requirements.txt > /tmp/requirements-runtime.txt \
    && python -m pip install -r /tmp/requirements-runtime.txt \
    && rm /tmp/requirements-runtime.txt

COPY agent ./agent
COPY db ./db
COPY evaluation ./evaluation
COPY evaluation_data ./evaluation_data
COPY ingestion ./ingestion
COPY ntsb ./ntsb
COPY rag ./rag
COPY configure.py ./configure.py

USER app
CMD ["python", "--version"]

FROM base AS dashboard

COPY dashboard/requirements.txt ./dashboard/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r dashboard/requirements.txt

COPY dashboard ./dashboard
COPY .streamlit ./.streamlit

USER app
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2)"
CMD ["streamlit", "run", "dashboard/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
