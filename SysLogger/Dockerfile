FROM python:3.9-slim

# Установка системных зависимостей и утилит для температур
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    lm-sensors \
    smartmontools \
    && rm -rf /var/lib/apt/lists/*

# Установка Python пакетов
RUN pip install --no-cache-dir psutil

# Создаем директорию для приложения
WORKDIR /app

# Копируем приложение
COPY app.py .

# Создаем директорию для логов
RUN mkdir -p /logs

# Запускаем приложение
CMD ["python", "-u", "app.py"]