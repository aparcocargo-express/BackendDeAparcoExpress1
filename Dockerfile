FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && pip install -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--log-file", "-"]

