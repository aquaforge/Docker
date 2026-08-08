import numpy as np
import datetime
import time
import os
import logging

# Создаем директорию logs, если её нет
os.makedirs('logs', exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/matrix_log.txt'),
        logging.StreamHandler()  # Также выводим в консоль
    ]
)

def process_matrix():
    """Основная функция обработки матрицы"""
    try:
        # Генерируем случайную матрицу 1000x1000
        matrix = np.random.rand(1000, 1000).astype(np.float64)
        
        # Умножаем матрицу саму на себя 100 раз
        result = matrix.copy()
        for i in range(100):
            result = result @ matrix
        
            # Нормализуем матрицу, разделив на максимальное значение
            max_value = np.max(result)
            if max_value != 0:  # Защита от деления на ноль
                result = result / max_value
            else:
                logging.warning("Максимальное значение равно 0, нормализация пропущена")
        
        # Логируем максимальное значение исходной матрицы
        logging.info(f"{max_value} - {np.average(result)}")
        
        # Опционально: можно также логировать максимальное значение нормализованной матрицы
        # (оно должно быть равно 1.0)
        # logging.info(f"Нормализованная матрица, макс значение: {np.max(normalized_result)}")
        
        return result
        
    except Exception as e:
        logging.error(f"Ошибка: {str(e)}")
        return None

def main():
    """Главный цикл программы"""
    while True:
        process_matrix()
        time.sleep(7)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрограмма остановлена пользователем")
    except Exception as e:
        logging.error(f"Критическая ошибка: {str(e)}")
        raise