#!/usr/bin/env python3
import psutil
import time
import logging
import signal
import sys
from datetime import datetime
import os
import subprocess
import re

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
    if signum in (signal.SIGTERM, signal.SIGINT):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        running = False
    else:
        logger.warning(f"Received unknown signal {signum}")

def get_cpu_temperature_psutil():
    """Получение температуры через psutil"""
    try:
        sensors = psutil.sensors_temperatures()
        if sensors:
            # Пробуем разные возможные названия для CPU температуры
            for sensor_name in ['coretemp', 'cpu-thermal', 'cpu_thermal', 'k10temp', 'acpitz']:
                if sensor_name in sensors:
                    temp = sensors[sensor_name][0].current
                    if temp > 0:
                        return temp
        return None
    except Exception as e:
        logger.debug(f"psutil sensors_temperatures failed: {e}")
        return None

def get_cpu_temperature_sysfs():
    """Получение температуры через /sys/class/thermal/thermal_zone"""
    try:
        thermal_zones = '/sys/class/thermal/thermal_zone'
        if os.path.exists(thermal_zones):
            for zone in os.listdir(thermal_zones):
                temp_file = os.path.join(thermal_zones, zone, 'temp')
                if os.path.exists(temp_file):
                    with open(temp_file, 'r') as f:
                        temp_raw = f.read().strip()
                        if temp_raw:
                            # Температура обычно в миллиградусах Цельсия
                            temp = float(temp_raw) / 1000.0
                            if temp > 0 and temp < 150:  # Реалистичные значения
                                return temp
        return None
    except Exception as e:
        logger.debug(f"sysfs temperature reading failed: {e}")
        return None

def get_cpu_temperature_sensors():
    """Получение температуры через команду sensors (lm-sensors)"""
    try:
        # Проверяем, установлена ли утилита sensors
        result = subprocess.run(['which', 'sensors'], 
                              capture_output=True, text=True, timeout=2)
        if result.returncode != 0:
            return None
            
        # Запускаем sensors и парсим вывод
        result = subprocess.run(['sensors'], 
                              capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            # Ищем строки с температурой CPU
            lines = result.stdout.split('\n')
            for line in lines:
                # Ищем паттерны типа: "Core 0:       +45.0°C"
                # или "temp1:        +45.0°C"
                match = re.search(r'([\+]?(\d+\.?\d*))°C', line)
                if match:
                    temp = float(match.group(1))
                    if temp > 0 and temp < 150:
                        return temp
        return None
    except Exception as e:
        logger.debug(f"sensors command failed: {e}")
        return None

def get_cpu_temperature():
    """Получение температуры CPU с использованием нескольких методов"""
    # Пробуем методы по порядку
    methods = [
        ('psutil', get_cpu_temperature_psutil),
        ('sysfs', get_cpu_temperature_sysfs),
        ('sensors', get_cpu_temperature_sensors)
    ]
    
    for method_name, method in methods:
        try:
            temp = method()
            if temp is not None and temp > 0:
                logger.debug(f"Temperature obtained via {method_name}: {temp}°C")
                return temp
        except Exception as e:
            logger.debug(f"Method {method_name} failed: {e}")
            continue
    
    # Если ничего не сработало, возвращаем 0
    logger.debug("All temperature methods failed, returning 0")
    return 0.0

def get_system_stats():
    """Получение системных метрик в формате key=value pairs"""
    try:
        # Текущее время с миллисекундами
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
        # Температура процессора
        cpu_temp = get_cpu_temperature()
        
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
            'cpu_temp': round(cpu_temp, 2),
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
        log_file = '/logs/app.log'
        log_dir = os.path.dirname(log_file)
        
        # Создаем директорию если её нет (с проверкой прав)
        if not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, mode=0o755, exist_ok=True)
            except PermissionError:
                logger.error(f"Permission denied to create {log_dir}")
                return
        
        # Формируем строку лога
        log_line = (f"timestamp={stats['timestamp']} "
                   f"cpu_temp={stats['cpu_temp']}°C "
                   f"cpu_usage={stats['cpu_usage']}% "
                   f"memory_usage={stats['memory_usage']}% "
                   f"disk_usage={stats['disk_usage']}%\n")
        
        # Записываем в файл с обработкой ошибок
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_line)
                f.flush()  # Принудительный сброс буфера
        except IOError as e:
            logger.error(f"IO Error writing to log file: {e}")
        except PermissionError:
            logger.error(f"Permission denied writing to {log_file}")
            
    except Exception as e:
        logger.error(f"Unexpected error writing to log file: {e}")

def main():
    """Главная функция программы"""
    global running
    
    # Устанавливаем обработчики сигналов
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("Application started successfully")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    
    # Проверяем доступность /logs
    try:
        if os.path.exists('/logs'):
            logger.info("Logs directory exists")
            test_file = '/logs/.write_test'
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            logger.info("Logs directory is writable")
        else:
            logger.warning("Logs directory does not exist, will try to create")
    except Exception as e:
        logger.error(f"Logs directory check failed: {e}")
    
    # Тестируем получение температуры при старте
    test_temp = get_cpu_temperature()
    logger.info(f"Initial CPU temperature test: {test_temp}°C")
    
    iterations = 0
    try:
        while running:
            iterations += 1
            stats = get_system_stats()
            write_log_entry(stats)
            
            if iterations % 10 == 0:  # Логируем каждые 20 секунд (10 * 2 секунды)
                logger.info(f"Still running, iteration {iterations}")
                # Периодически выводим текущую температуру в логи для отладки
                current_temp = stats['cpu_temp'] if stats else 0
                logger.info(f"Current temperature: {current_temp}°C")
            
            # Ждем 2 секунды, но проверяем флаг каждые 0.1 секунды
            for _ in range(20):
                if not running:
                    break
                time.sleep(0.1)
                
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")
        sys.exit(1)
    finally:
        logger.info(f"Application stopped after {iterations} iterations")
        sys.exit(0)

if __name__ == "__main__":
    main()