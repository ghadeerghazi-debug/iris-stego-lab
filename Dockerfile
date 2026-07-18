FROM python:3.13-slim

# libglib2.0-0 provides libgthread, required by opencv-python-headless at import time
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD uvicorn app:app --host 0.0.0.0 --port $PORT
