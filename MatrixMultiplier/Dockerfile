FROM python:3.11-slim

WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY matrix_multiplier.py .

# Создаем директорию для логов
RUN mkdir -p /app/logs

# Запускаем программу
CMD ["python", "matrix_multiplier.py"]