#!/usr/bin/env python3
import docker
import socket
import psutil
import os
import logging
import subprocess
import re
import requests
from flask import Flask, render_template_string, jsonify, request, Response
from datetime import datetime
import prometheus_client
from prometheus_client import Gauge, generate_latest, REGISTRY

app = Flask(__name__)
docker_client = docker.from_env()

# Фильтр для подавления логов /api/stats
class SuppressStatsLogs(logging.Filter):
    def filter(self, record):
        return '/api/stats' not in record.getMessage()

logging.getLogger('werkzeug').addFilter(SuppressStatsLogs())

# Общие метрики
cpu_usage_total = Gauge('system_cpu_usage_percent', 'Total CPU usage percentage')
cpu_temp = Gauge('system_cpu_temperature_celsius', 'CPU temperature in Celsius')
gpu_temp = Gauge('system_gpu_temperature_celsius', 'GPU temperature in Celsius')
disk_temp = Gauge('system_disk_temperature_celsius', 'Disk temperature in Celsius')
memory_usage = Gauge('system_memory_usage_percent', 'Memory usage percentage')
memory_used_gb = Gauge('system_memory_used_gb', 'Memory used in GB')
disk_usage_percent = Gauge('system_disk_usage_percent', 'Disk usage percentage')
container_count = Gauge('docker_container_count', 'Total number of containers')
container_running = Gauge('docker_container_running', 'Number of running containers')

# Метрики для каждого ядра CPU
cpu_core_gauges = {}

def get_cpu_core_usage():
    """Получение загрузки каждого ядра CPU"""
    try:
        cpu_percents = psutil.cpu_percent(interval=0.1, percpu=True)
        
        for i, percent in enumerate(cpu_percents):
            core_name = f'core_{i}'
            if core_name not in cpu_core_gauges:
                cpu_core_gauges[core_name] = Gauge(
                    f'system_cpu_core_{i}_usage_percent',
                    f'CPU Core {i} usage percentage',
                    ['core']
                )
            cpu_core_gauges[core_name].labels(core=core_name).set(percent)
        
        return cpu_percents
    except Exception as e:
        print(f"Error getting CPU core usage: {e}")
        return []

def get_server_ip():
    """Определяем IP сервера для ссылок"""
    try:
        if request:
            host = request.host.split(':')[0]
            if host not in ['localhost', '127.0.0.1']:
                return host
    except:
        pass
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return 'localhost'

def get_cpu_temperature():
    """Получение температуры CPU - ТОЛЬКО CPU"""
    try:
        # Способ 1: /sys/class/thermal (основной для CPU)
        if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read().strip()) / 1000.0
                if 20 < temp < 120:  # Реалистичный диапазон для CPU
                    print(f"CPU temp from thermal_zone0: {temp}°C")
                    return temp
        
        # Способ 2: sensors для CPU
        try:
            result = subprocess.run(['sensors', '-u'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                # Ищем только CPU (coretemp, k10temp, etc.)
                in_cpu_section = False
                for line in result.stdout.split('\n'):
                    # Определяем секцию CPU
                    if 'coretemp' in line.lower() or 'k10temp' in line.lower() or 'cpu' in line.lower():
                        in_cpu_section = True
                    if in_cpu_section and 'temp1_input' in line:
                        match = re.search(r'(\d+\.\d+)', line)
                        if match:
                            temp = float(match.group(1))
                            if 20 < temp < 120:
                                print(f"CPU temp from sensors: {temp}°C")
                                return temp
        except:
            pass
        
        # Способ 3: vcgencmd для Raspberry Pi
        try:
            result = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                match = re.search(r'(\d+\.\d+)', result.stdout)
                if match:
                    temp = float(match.group(1))
                    if 20 < temp < 120:
                        print(f"CPU temp from vcgencmd: {temp}°C")
                        return temp
        except:
            pass
        
        return None
    except Exception as e:
        print(f"Error getting CPU temperature: {e}")
        return None

def get_gpu_temperature():
    """Получение температуры GPU - ТОЛЬКО GPU"""
    try:
        # Способ 1: NVIDIA GPU через nvidia-smi
        if os.path.exists('/usr/bin/nvidia-smi'):
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader'], 
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                temp = float(result.stdout.strip())
                if 20 < temp < 120:
                    print(f"GPU temp from nvidia-smi: {temp}°C")
                    return temp
        
        # Способ 2: AMD GPU через sensors
        try:
            result = subprocess.run(['sensors', '-u'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                in_gpu_section = False
                for line in result.stdout.split('\n'):
                    # Определяем секцию GPU
                    if 'amdgpu' in line.lower() or 'radeon' in line.lower() or 'nouveau' in line.lower():
                        in_gpu_section = True
                    if in_gpu_section and 'temp1_input' in line:
                        match = re.search(r'(\d+\.\d+)', line)
                        if match:
                            temp = float(match.group(1))
                            if 20 < temp < 120:
                                print(f"GPU temp from sensors: {temp}°C")
                                return temp
        except:
            pass
        
        # Способ 3: Intel GPU через sysfs
        try:
            if os.path.exists('/sys/class/drm/card0/device/hwmon/hwmon0/temp1_input'):
                with open('/sys/class/drm/card0/device/hwmon/hwmon0/temp1_input', 'r') as f:
                    temp = float(f.read().strip()) / 1000.0
                    if 20 < temp < 120:
                        print(f"GPU temp from sysfs: {temp}°C")
                        return temp
        except:
            pass
        
        # Способ 4: GPU через node_exporter (если доступен)
        try:
            response = requests.get('http://node-exporter:9100/metrics', timeout=2)
            if response.status_code == 200:
                for line in response.text.split('\n'):
                    # Ищем GPU в метриках
                    if 'node_hwmon_temp_celsius' in line and ('gpu' in line.lower() or 'amdgpu' in line.lower()):
                        match = re.search(r'node_hwmon_temp_celsius\{[^}]*\}\s+([\d.]+)', line)
                        if match:
                            temp = float(match.group(1))
                            if 20 < temp < 120:
                                print(f"GPU temp from node_exporter: {temp}°C")
                                return temp
        except:
            pass
        
        return None
    except Exception as e:
        print(f"Error getting GPU temperature: {e}")
        return None

def get_disk_temperature():
    """Получение температуры диска - ТОЛЬКО диск"""
    try:
        # Способ 1: hddtemp для SATA дисков
        try:
            for disk in ['sda', 'sdb', 'sdc', 'sdd']:
                result = subprocess.run(
                    ['hddtemp', '-n', f'/dev/{disk}'], 
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    temp = float(result.stdout.strip())
                    if 20 < temp < 80:  # Реалистичный диапазон для диска
                        print(f"Disk temp from hddtemp /dev/{disk}: {temp}°C")
                        return temp
        except Exception as e:
            print(f"hddtemp error: {e}")
        
        # Способ 2: smartctl для SATA дисков
        try:
            result = subprocess.run(
                ['lsblk', '-d', '-o', 'NAME,TYPE'], 
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'disk' in line.lower() and line.strip().startswith('sd'):
                        disk = line.split()[0]
                        smart_result = subprocess.run(
                            ['smartctl', '-A', f'/dev/{disk}'], 
                            capture_output=True, text=True, timeout=3
                        )
                        if smart_result.returncode == 0:
                            for line in smart_result.stdout.split('\n'):
                                if 'Temperature_Celsius' in line:
                                    parts = line.split()
                                    for part in parts:
                                        try:
                                            temp = float(part)
                                            if 20 < temp < 80:
                                                print(f"Disk temp from smartctl /dev/{disk}: {temp}°C")
                                                return temp
                                        except:
                                            continue
        except Exception as e:
            print(f"smartctl error: {e}")
        
        # Способ 3: NVMe диски
        try:
            for disk in ['nvme0n1', 'nvme1n1']:
                temp_path = f'/sys/block/{disk}/device/temperature'
                if os.path.exists(temp_path):
                    with open(temp_path, 'r') as f:
                        temp = float(f.read().strip())
                        if 20 < temp < 80:
                            print(f"Disk temp from NVMe {disk}: {temp}°C")
                            return temp
        except:
            pass
        
        # Способ 4: drivetemp через sysfs
        try:
            for root, dirs, files in os.walk('/sys/class/hwmon/'):
                for dir in dirs:
                    if dir.startswith('hwmon'):
                        hwmon_dir = os.path.join(root, dir)
                        # Проверяем, что это диск, а не CPU
                        if 'disk' in dir.lower() or 'drive' in dir.lower():
                            temp_file = os.path.join(hwmon_dir, 'temp1_input')
                            if os.path.exists(temp_file):
                                with open(temp_file, 'r') as f:
                                    temp = float(f.read().strip())
                                    if temp > 1000:
                                        temp = temp / 1000.0
                                    if 20 < temp < 80:
                                        print(f"Disk temp from drivetemp: {temp}°C")
                                        return temp
        except:
            pass
        
        # Способ 5: disk через node_exporter
        try:
            response = requests.get('http://node-exporter:9100/metrics', timeout=2)
            if response.status_code == 200:
                for line in response.text.split('\n'):
                    if 'node_hwmon_temp_celsius' in line and ('disk' in line.lower() or 'drive' in line.lower()):
                        match = re.search(r'node_hwmon_temp_celsius\{[^}]*\}\s+([\d.]+)', line)
                        if match:
                            temp = float(match.group(1))
                            if 20 < temp < 80:
                                print(f"Disk temp from node_exporter: {temp}°C")
                                return temp
        except:
            pass
        
        return None
    except Exception as e:
        print(f"Error getting disk temperature: {e}")
        return None

def get_system_stats():
    """Получаем статистику системы"""
    try:
        # CPU - общая загрузка
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_freq = psutil.cpu_freq()
        
        # Загрузка каждого ядра
        cpu_core_percents = get_cpu_core_usage()
        
        # Температуры (каждая из своего источника)
        cpu_temp_value = get_cpu_temperature()
        gpu_temp_value = get_gpu_temperature()
        disk_temp_value = get_disk_temperature()
        
        # Память
        memory = psutil.virtual_memory()
        
        # Диск
        disk = psutil.disk_usage('/')
        
        # Считаем контейнеры
        containers = docker_client.containers.list(all=True)
        running = [c for c in containers if c.status == 'running']
        
        # Обновляем Prometheus метрики
        cpu_usage_total.set(cpu_percent)
        memory_usage.set(memory.percent)
        memory_used_gb.set(round(memory.used / (1024**3), 1))
        disk_usage_percent.set(disk.percent)
        container_count.set(len(containers))
        container_running.set(len(running))
        
        # Обновляем метрики температуры
        if cpu_temp_value is not None:
            cpu_temp.set(cpu_temp_value)
        if gpu_temp_value is not None:
            gpu_temp.set(gpu_temp_value)
        if disk_temp_value is not None:
            disk_temp.set(disk_temp_value)
        
        # Формируем данные для ответа
        result = {
            'cpu_percent': round(cpu_percent, 1),
            'cpu_freq': round(cpu_freq.current, 0) if cpu_freq else None,
            'cpu_temp': round(cpu_temp_value, 1) if cpu_temp_value else None,
            'gpu_temp': round(gpu_temp_value, 1) if gpu_temp_value else None,
            'disk_temp': round(disk_temp_value, 1) if disk_temp_value else None,
            'memory_used': round(memory.used / (1024**3), 1),
            'memory_total': round(memory.total / (1024**3), 1),
            'memory_percent': memory.percent,
            'disk_used': round(disk.used / (1024**3), 1),
            'disk_total': round(disk.total / (1024**3), 1),
            'disk_percent': disk.percent,
            'containers_total': len(containers),
            'containers_running': len(running),
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
        
        # Добавляем данные по каждому ядру
        for i, percent in enumerate(cpu_core_percents):
            result[f'cpu_core_{i}_percent'] = round(percent, 1)
        
        return result
    except Exception as e:
        print(f"Stats error: {e}")
        return {
            'error': str(e),
            'cpu_percent': 0,
            'cpu_temp': None,
            'gpu_temp': None,
            'disk_temp': None,
            'memory_used': 0,
            'memory_total': 0,
            'memory_percent': 0,
            'disk_used': 0,
            'disk_total': 0,
            'disk_percent': 0,
            'containers_total': 0,
            'containers_running': 0,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }

# HTML_TEMPLATE (используйте из предыдущего ответа)

@app.route('/')
def index():
    server_ip = get_server_ip()
    containers_data = []
    running_count = 0
    
    try:
        containers = docker_client.containers.list(all=True)
        
        for container in containers:
            if container.status == 'running':
                running_count += 1
                
            ports_info = []
            seen_ports = set()
            
            if container.attrs['NetworkSettings']['Ports']:
                for container_port, host_bindings in container.attrs['NetworkSettings']['Ports'].items():
                    if host_bindings:
                        for binding in host_bindings:
                            port_key = f"{binding['HostPort']}-{container_port}"
                            if port_key not in seen_ports:
                                seen_ports.add(port_key)
                                ports_info.append({
                                    'container_port': container_port.split('/')[0],
                                    'type': container_port.split('/')[1] if '/' in container_port else 'tcp',
                                    'host_port': binding['HostPort'],
                                    'host_ip': binding['HostIp']
                                })
            
            containers_data.append({
                'name': container.name,
                'status': container.status,
                'image': container.image.tags[0] if container.image.tags else container.image.id[:12],
                'ports': ports_info,
                'id': container.id[:12]
            })
    except Exception as e:
        return f"Error: {str(e)}", 500
    
    stats = get_system_stats()
    
    def get_color(value):
        if value < 50:
            return 'good'
        elif value < 75:
            return 'warning'
        return 'danger'
    
    stats['cpu_color'] = get_color(stats['cpu_percent'])
    stats['memory_color'] = get_color(stats['memory_percent'])
    stats['disk_color'] = get_color(stats['disk_percent'])
    
    cpu_cores_count = psutil.cpu_count()
    
    return render_template_string(
        HTML_TEMPLATE, 
        containers=containers_data, 
        server_ip=server_ip,
        stats=stats,
        running_count=running_count,
        cpu_cores_count=cpu_cores_count
    )

@app.route('/api/stats')
def api_stats():
    """API endpoint для получения статистики"""
    return jsonify(get_system_stats())

@app.route('/metrics')
def metrics():
    """Endpoint для Prometheus"""
    return Response(generate_latest(REGISTRY), mimetype='text/plain')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)