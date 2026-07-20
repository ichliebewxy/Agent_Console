FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm poppler-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pymupdf pypdf reportlab

WORKDIR /workspace

CMD ["/bin/sh"]
