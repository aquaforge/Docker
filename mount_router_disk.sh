#!/bin/bash

# apt update && apt install cifs-utils -y
# mkdir /mnt/router_disk

# nano mount_router_disk.sh
# chmod +x mount_router_disk.sh
# to run ./mount_router_disk.sh

# Простой скрипт для монтирования сетевой папки
mount.cifs //192.168.1.1/EXT4-e8WiPOOI /mnt/router_disk

# Для открытой (гостевой) папки без пароля в /etc/fstab
# //192.168.1.1/EXT4-e8WiPOOI /mnt/router_disk cifs guest,uid=1000,gid=1000,iocharset=utf8,file_mode=0777,dir_mode=0777 0 0


# Проверить статус: nmcli radio wifi
# Включить nmcli radio wifi on
# nmcli radio wifi off


# nano /etc/.smbcredentials
#  username=
#  password=
#  nano /etc/fstab
#  //192.168.1.1/EXT4-e8WiPOOI /mnt/router_disk cifs credentials=/etc/.smbcredentials,uid=1000,gid=1000,iocharset=utf8,file_mode=0755,dir_mode=0755,noperm 0 0