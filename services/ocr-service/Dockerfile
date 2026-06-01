FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    unzip \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create directory for EasyOCR cached models
RUN mkdir -p /root/.EasyOCR/model

# Download and unpack EasyOCR models during build to support offline execution
RUN wget -q -O /tmp/craft_mlt_25k.zip https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip && \
    unzip -q /tmp/craft_mlt_25k.zip -d /root/.EasyOCR/model && \
    rm /tmp/craft_mlt_25k.zip

RUN wget -q -O /tmp/arabic.zip https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/arabic.zip && \
    unzip -q /tmp/arabic.zip -d /root/.EasyOCR/model && \
    rm /tmp/arabic.zip

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
