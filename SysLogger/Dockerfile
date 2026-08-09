FROM python:3.9-slim

# Устанавливаем переменные окружения для Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Устанавливаем системные зависимости и утилиты для температуры
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    lm-sensors \
    smartmontools \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Устанавливаем Python пакеты отдельно для лучшего кеширования
# Копируем requirements.txt если есть, иначе устанавливаем psutil
COPY requirements.txt ./
RUN if [ -f requirements.txt ]; then pip install -r requirements.txt; else pip install --no-cache-dir psutil; fi

# Создаем директории
RUN mkdir -p /app /logs

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем приложение
COPY app.py .

# Healthcheck для Docker
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep -f "python -u app.py" || exit 1

# Запускаем приложение
CMD ["python", "-u", "app.py"]