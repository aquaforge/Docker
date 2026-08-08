FROM python:3.9-slim

WORKDIR /app

# Установка системных зависимостей и утилит для температур
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    lm-sensors \
    smartmontools \
    && rm -rf /var/lib/apt/lists/*

# Установка Python пакетов
RUN pip install --no-cache-dir flask docker psutil prometheus-client

COPY app.py .

EXPOSE 80

CMD ["python", "app.py"]