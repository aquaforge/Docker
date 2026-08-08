import numpy as np
import datetime
import time
import os
import logging
import signal
import sys
import gc  # Добавляем сборщик мусора

# Глобальный флаг для управления циклом
running = True

# Создаем директорию logs, если её нет
os.makedirs('logs', exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/matrix_log.txt'),
        logging.StreamHandler()
    ]
)

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения"""
    global running
    logging.info(f"Получен сигнал {signum}. Завершение работы...")
    running = False

# Регистрируем обработчики сигналов
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def process_matrix():
    """Основная функция обработки матрицы"""
    try:
        # Используем меньший тип данных для экономии памяти
        matrix = np.random.rand(1000, 1000).astype(np.float32)
        
        # Умножаем матрицу саму на себя 100 раз
        result = matrix.copy()
        for i in range(100):
            if not running:
                logging.info("Прерывание операции умножения")
                return None
            
            # Освобождаем память после каждой итерации
            if i > 0:
                del matrix
                gc.collect()
            
            matrix = result.copy()
            result = result @ matrix
            result = result / np.max(result)
        
        # Находим максимальное значение
        max_value = np.max(result)
        
        # Нормализуем матрицу
        if max_value != 0:
            normalized_result = result / max_value
        else:
            normalized_result = result
            logging.warning("Максимальное значение равно 0, нормализация пропущена")
        
        # Логируем максимальное значение
        logging.info(f"{max_value} {np.average(result)} {np.min(result)}")
        
        # Освобождаем память
        del result, matrix, normalized_result
        gc.collect()
        
        return True
        
    except MemoryError as e:
        logging.error(f"Ошибка памяти: {str(e)}")
        gc.collect()
        time.sleep(10)
        return None
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
        gc.collect()
        return None

def main():
    """Главный цикл программы"""
    global running
    
    logging.info("Программа запущена. Ожидание сигналов для завершения...")
    
    while running:
        process_matrix()
        
        if not running:
            break
            
        # # Сон с возможностью прерывания
        # for _ in range(7):
        #     if not running:
        #         break
        #     time.sleep(1)
    
    logging.info("Программа завершена корректно")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Программа остановлена пользователем (Ctrl+C)")
    except Exception as e:
        logging.error(f"Критическая ошибка: {str(e)}")
        sys.exit(1)
    finally:
        logging.info("Очистка ресурсов...")
        gc.collect()
        sys.exit(0)