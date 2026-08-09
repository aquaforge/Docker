#!/usr/bin/env python3
import psutil
import time
import logging
import signal
import sys
from datetime import datetime
import os

# Настройка логирования для самой программы (только ошибки в stdout)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Флаг для graceful shutdown
running = True

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    global running
    logger.info("Received stop signal, shutting down...")
    running = False

def get_system_stats():
    """Получение системных метрик в формате key=value pairs"""
    try:
        # Текущее время с миллисекундами
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Температура процессора (если доступна)
        try:
            cpu_temp = psutil.sensors_temperatures()
            if cpu_temp and 'coretemp' in cpu_temp:
                temp = cpu_temp['coretemp'][0].current
            else:
                temp = 0.0
        except:
            temp = 0.0
        
        # Загрузка процессора
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # Загрузка оперативной памяти
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Объем занятого диска (для корневой файловой системы)
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        
        return {
            'timestamp': timestamp,
            'cpu_temp': round(temp, 2),
            'cpu_usage': round(cpu_percent, 2),
            'memory_usage': round(memory_percent, 2),
            'disk_usage': round(disk_percent, 2)
        }
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        return None

def write_log_entry(stats):
    """Запись лога в файл в формате key=value pairs"""
    if stats is None:
        return
    
    try:
        log_dir = '/logs'
        log_file = '/logs/app.log'
        
        # Создаем директорию если её нет
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Формируем строку лога
        log_line = f"timestamp={stats['timestamp']} cpu_temp={stats['cpu_temp']}°C cpu_usage={stats['cpu_usage']}% memory_usage={stats['memory_usage']}% disk_usage={stats['disk_usage']}%\n"
        
        # Записываем в файл
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_line)
            
    except Exception as e:
        logger.error(f"Error writing to log file: {e}")

def main():
    """Главная функция программы"""
    global running
    
    # Устанавливаем обработчики сигналов
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("Application started successfully")
    
    try:
        while running:
            stats = get_system_stats()
            write_log_entry(stats)
            
            # Ждем 2 секунды, но проверяем флаг каждые 0.1 секунды
            # для более быстрой реакции на сигналы остановки
            for _ in range(20):
                if not running:
                    break
                time.sleep(0.1)
                
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")
        sys.exit(1)
    finally:
        logger.info("Application stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()