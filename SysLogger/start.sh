#!/bin/bash

# chmod +x start.sh
# ./start.sh

# Создаем необходимые директории
mkdir -p logs
mkdir -p grafana_data
mkdir -p loki_data
mkdir -p grafana-provisioning/datasources
mkdir -p grafana-provisioning/dashboards

# Устанавливаем правильные права
chmod -R 777 grafana_data
chmod -R 777 loki_data

# Запускаем docker-compose
# docker-compose up -d

# echo "========================================="
# echo "Система запущена!"
# echo "Grafana: http://localhost:3000"
# echo "  Login: admin/admin"
# echo "Promtail: http://localhost:9080"
# echo "Loki: http://localhost:3100"
# echo "========================================="
# echo ""
# echo "Для просмотра логов: docker-compose logs -f"
# echo "Для остановки: docker-compose down"