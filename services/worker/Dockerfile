FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY services/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/backend-core /app/backend-core
ENV PYTHONPATH=/app/backend-core

CMD ["python", "-m", "arq", "app.worker.WorkerSettings"]
