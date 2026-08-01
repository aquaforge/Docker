#!/bin/bash

# apt update && apt install cifs-utils -y
# mkdir /mnt/router_disk

# nano mount_router_disk.sh
# chmod +x mount_router_disk.sh
# to run ./mount_router_disk.sh

# Простой скрипт для монтирования сетевой папки
mount.cifs //192.168.1.1/EXT4-e8WiPOOI /mnt/router_disk


# Проверить статус: nmcli radio wifi
# Включить nmcli radio wifi on
# nmcli radio wifi off
