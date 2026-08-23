-- Таблица для системных метрик
CREATE TABLE IF NOT EXISTS system_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    cpu_temp FLOAT,
    cpu_usage FLOAT,
    memory_usage FLOAT,
    disk_usage FLOAT
);

-- Индекс для быстрых запросов по времени
CREATE INDEX IF NOT EXISTS idx_system_metrics_timestamp ON system_metrics(timestamp);

-- Создаем пользователя для Grafana с правами только на чтение
CREATE USER IF NOT EXISTS grafana_reader WITH PASSWORD 'readonly';
GRANT SELECT ON system_metrics TO grafana_reader;