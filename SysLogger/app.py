#!/usr/bin/env python3
import psutil
import time
import logging
import signal
import sys
from datetime import datetime
import os
import json

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
    """Получение системных метрик в JSON формате"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        
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

def write_log_entry(stats):
    """Запись лога в файл в JSON формате"""
    if stats is None:
        return
    
    try:
        log_file = '/logs/app.log'
        log_dir = os.path.dirname(log_file)
        
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, mode=0o755, exist_ok=True)
        
        # Записываем в JSON формате
        with open(log_file, 'a', encoding='utf-8') as f:
            json.dump(stats, f)
            f.write('\n')  # Каждая запись на новой строке
            f.flush()
            
    except Exception as e:
        logger.error(f"Error writing to log file: {e}")

def main():
    global running
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info("Application started successfully")
    logger.info(f"Python version: {sys.version}")
    
    iterations = 0
    try:
        while running:
            iterations += 1
            stats = get_system_stats()
            write_log_entry(stats)
            
            if iterations % 10 == 0:
                logger.info(f"Still running, iteration {iterations}")
            
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