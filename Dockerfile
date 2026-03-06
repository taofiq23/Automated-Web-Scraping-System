FROM mcr.microsoft.com/playwright/python:v1.54.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install -e . \
    && playwright install chromium \
    && mkdir -p /app/output

CMD ["python", "-m", "multi_scrap.cli", "run-weekly", "--current-week", "--publish-gsheets"]
