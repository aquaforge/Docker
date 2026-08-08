FROM python:3.11-slim

# Устанавливаем переменные окружения для Python
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY matrix_multiplier.py .

# Создаем директорию для логов
RUN mkdir -p /app/logs

# Используем exec форму для правильной обработки сигналов
CMD ["python", "-u", "matrix_multiplier.py"]