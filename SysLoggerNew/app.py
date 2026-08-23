#!/usr/bin/env python3
import psutil
import time
import logging
import signal
import sys
from datetime import datetime
import os
import json
from sqlalchemy import create_engine, Column, Integer, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

running = True

# Настройка PostgreSQL
POSTGRES_USER = os.getenv('POSTGRES_USER', 'admin')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'k4h5k8ow7')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'server_stats')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres')  # имя контейнера PostgreSQL
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Создаем движок SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Проверка соединения перед использованием
    echo=False  # Установить True для отладки SQL-запросов
)

# Создаем базовый класс для моделей
Base = declarative_base()

# Определяем модель для системных метрик


class SystemMetric(Base):
    __tablename__ = 'system_metrics'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    cpu_temp = Column(Float)
    cpu_usage = Column(Float)
    memory_usage = Column(Float)
    disk_usage = Column(Float)

    def __repr__(self):
        return f"<SystemMetric(timestamp={self.timestamp}, cpu_temp={self.cpu_temp})>"


# Создаем сессию
SessionLocal = sessionmaker(bind=engine, autoflush=True, autocommit=False)


def signal_handler(signum, frame):
    global running
    if signum in (signal.SIGTERM, signal.SIGINT):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        running = False


def get_cpu_temperature():
    """Получение температуры CPU"""
    try:
        # Пробуем через psutil
        sensors = psutil.sensors_temperatures()
        if sensors:
            for sensor_name in ['coretemp', 'cpu-thermal', 'cpu_thermal', 'k10temp', 'acpitz']:
                if sensor_name in sensors:
                    temp = sensors[sensor_name][0].current
                    if temp > 0:
                        return round(temp, 2)

        # Пробуем через sysfs
        thermal_zones = '/sys/class/thermal/thermal_zone'
        if os.path.exists(thermal_zones):
            for zone in os.listdir(thermal_zones):
                temp_file = os.path.join(thermal_zones, zone, 'temp')
                if os.path.exists(temp_file):
                    with open(temp_file, 'r') as f:
                        temp_raw = f.read().strip()
                        if temp_raw:
                            temp = float(temp_raw) / 1000.0
                            if temp > 0 and temp < 150:
                                return round(temp, 2)
        return 0.0
    except Exception as e:
        logger.debug(f"Temperature reading failed: {e}")
        return 0.0


def get_system_stats():
    """Получение системных метрик"""
    try:
        timestamp = datetime.now()

        return {
            'timestamp': timestamp,
            'cpu_temp': get_cpu_temperature(),
            'cpu_usage': round(psutil.cpu_percent(interval=0.1), 2),
            'memory_usage': round(psutil.virtual_memory().percent, 2),
            'disk_usage': round(psutil.disk_usage('/').percent, 2)
        }
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        return None


def save_to_postgres(stats):
    """Сохранение метрик в PostgreSQL"""
    if stats is None:
        return False

    session = SessionLocal()
    try:
        # Создаем запись
        metric = SystemMetric(
            timestamp=stats['timestamp'],
            cpu_temp=stats['cpu_temp'],
            cpu_usage=stats['cpu_usage'],
            memory_usage=stats['memory_usage'],
            disk_usage=stats['disk_usage']
        )

        session.add(metric)
        session.commit()
        logger.debug(f"Saved metric to PostgreSQL: {stats['timestamp']}")
        return True

    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error: {e}")
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving to PostgreSQL: {e}")
        return False
    finally:
        session.close()


def write_log_entry(stats):
    """Запись лога в файл в JSON формате (для обратной совместимости)"""
    if stats is None:
        return

    try:
        log_file = '/logs/app.log'
        log_dir = os.path.dirname(log_file)

        if not os.path.exists(log_dir):
            os.makedirs(log_dir, mode=0o755, exist_ok=True)

        # Записываем в JSON формате
        with open(log_file, 'a', encoding='utf-8') as f:
            # Преобразуем datetime в строку для JSON
            stats_copy = stats.copy()
            stats_copy['timestamp'] = stats_copy['timestamp'].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            json.dump(stats_copy, f)
            f.write('\n')  # Каждая запись на новой строке
            f.flush()

    except Exception as e:
        logger.error(f"Error writing to log file: {e}")


def init_database():
    """Инициализация базы данных - создание таблицы если её нет"""
    try:
        Base.metadata.create_all(engine)
        logger.info("Database tables created/verified successfully")
        return True
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


def main():
    global running

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("Application started successfully")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"PostgreSQL connection: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")

    # Инициализация базы данных
    if not init_database():
        logger.warning("Database initialization failed, but continuing...")

    iterations = 0
    success_count = 0
    fail_count = 0

    try:
        while running:
            iterations += 1
            stats = get_system_stats()

            # Сохраняем в PostgreSQL
            if save_to_postgres(stats):
                success_count += 1
            else:
                fail_count += 1

            # Сохраняем в файл для обратной совместимости
            write_log_entry(stats)

            if iterations % 100 == 0:
                logger.info(f"Still running, iteration {iterations} (success: {success_count}, fails: {fail_count})")

            for _ in range(50): # (Х секунд)*10
                if not running:
                    break
                time.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")
        sys.exit(1)
    finally:
        logger.info(f"Application stopped after {iterations} iterations (success: {success_count}, fails: {fail_count})")
        sys.exit(0)


if __name__ == "__main__":
    main()


# SELECT
#     MIN(cpu_temp) AS min_cpu_temp,
#     MAX(cpu_temp) AS max_cpu_temp,
#     MIN(memory_usage) AS min_memory_usage,
#     MAX(memory_usage) AS max_memory_usage,
#     MIN(timestamp) AS earliest_time,
#     MAX(timestamp) AS latest_time
# FROM system_metrics;
