#!/usr/bin/env python3
import docker
import socket
import psutil
import os
import logging
import subprocess
import re
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

# Prometheus метрики
cpu_usage = Gauge('system_cpu_usage_percent', 'CPU usage percentage')
cpu_temp = Gauge('system_cpu_temperature_celsius', 'CPU temperature in Celsius')
gpu_temp = Gauge('system_gpu_temperature_celsius', 'GPU temperature in Celsius')
memory_usage = Gauge('system_memory_usage_percent', 'Memory usage percentage')
memory_used_gb = Gauge('system_memory_used_gb', 'Memory used in GB')
disk_usage_percent = Gauge('system_disk_usage_percent', 'Disk usage percentage')
container_count = Gauge('docker_container_count', 'Total number of containers')
container_running = Gauge('docker_container_running', 'Number of running containers')

def get_cpu_temperature():
    """Получение температуры CPU различными способами"""
    try:
        # Способ 1: Через /sys/class/thermal (Linux)
        if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                return float(f.read().strip()) / 1000.0
        
        # Способ 2: Через sensors (если установлен)
        try:
            result = subprocess.run(['sensors', '-u'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                # Ищем температуру CPU
                for line in result.stdout.split('\n'):
                    if 'temp1_input' in line or 'Core 0' in line:
                        match = re.search(r'(\d+\.\d+)', line)
                        if match:
                            return float(match.group(1))
        except:
            pass
        
        # Способ 3: Через vcgencmd (Raspberry Pi)
        try:
            result = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                match = re.search(r'(\d+\.\d+)', result.stdout)
                if match:
                    return float(match.group(1))
        except:
            pass
        
        # Способ 4: Через /proc/stat (не дает температуру, но оставляем как fallback)
        return None
    except Exception as e:
        print(f"Error getting CPU temperature: {e}")
        return None

def get_gpu_temperature():
    """Получение температуры GPU (NVIDIA)"""
    try:
        # Для NVIDIA GPU
        if os.path.exists('/usr/bin/nvidia-smi'):
            result = subprocess.run(['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader'], 
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        
        # Для AMD GPU (через sensors)
        try:
            result = subprocess.run(['sensors', '-u'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'amdgpu' in line.lower() or 'temp1_input' in line:
                        match = re.search(r'(\d+\.\d+)', line)
                        if match:
                            return float(match.group(1))
        except:
            pass
        
        return None
    except Exception as e:
        print(f"Error getting GPU temperature: {e}")
        return None

def get_disk_temperature():
    """Получение температуры диска (через smartctl)"""
    try:
        # Получаем список дисков
        result = subprocess.run(['lsblk', '-d', '-o', 'NAME,TYPE'], capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'disk' in line and 'nvme' in line.lower():
                    disk = line.split()[0]
                    # Для NVMe дисков
                    try:
                        smart_result = subprocess.run(['sudo', 'smartctl', '-A', f'/dev/{disk}'], 
                                                    capture_output=True, text=True, timeout=2)
                        if smart_result.returncode == 0:
                            for line in smart_result.stdout.split('\n'):
                                if 'Temperature:' in line or 'Temperature_Celsius' in line:
                                    match = re.search(r'(\d+)', line)
                                    if match:
                                        return float(match.group(1))
                    except:
                        pass
        return None
    except Exception as e:
        print(f"Error getting disk temperature: {e}")
        return None

def get_system_stats():
    """Получаем статистику системы"""
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_freq = psutil.cpu_freq()
        
        # Температуры
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
        cpu_usage.set(cpu_percent)
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
        
        return {
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

# Остальной код (HTML_TEMPLATE, routes) без изменений...
# Используйте HTML_TEMPLATE из предыдущего ответа

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
    
    return render_template_string(
        HTML_TEMPLATE, 
        containers=containers_data, 
        server_ip=server_ip,
        stats=stats,
        running_count=running_count
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