FROM python:3.11-slim-bookworm

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY pridepy ./pridepy

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir . \
 && rm -rf /src

WORKDIR /data
