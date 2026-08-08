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
    """Получение температуры CPU"""
    try:
        # Способ 1: /sys/class/thermal
        if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = float(f.read().strip()) / 1000.0
                if 20 < temp < 120:
                    return temp
        
        # Способ 2: sensors
        try:
            result = subprocess.run(['sensors', '-u'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                in_cpu_section = False
                for line in result.stdout.split('\n'):
                    if 'coretemp' in line.lower() or 'k10temp' in line.lower():
                        in_cpu_section = True
                    if in_cpu_section and 'temp1_input' in line:
                        match = re.search(r'(\d+\.\d+)', line)
                        if match:
                            temp = float(match.group(1))
                            if 20 < temp < 120:
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
                        return temp
        except:
            pass
        
        return None
    except Exception as e:
        print(f"Error getting CPU temperature: {e}")
        return None

def get_gpu_temperature():
    """Получение температуры GPU"""
    try:
        # Способ 1: NVIDIA GPU
        if os.path.exists('/usr/bin/nvidia-smi'):
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader'], 
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                temp = float(result.stdout.strip())
                if 20 < temp < 120:
                    return temp
        
        # Способ 2: AMD GPU через sensors
        try:
            result = subprocess.run(['sensors', '-u'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                in_gpu_section = False
                for line in result.stdout.split('\n'):
                    if 'amdgpu' in line.lower() or 'radeon' in line.lower():
                        in_gpu_section = True
                    if in_gpu_section and 'temp1_input' in line:
                        match = re.search(r'(\d+\.\d+)', line)
                        if match:
                            temp = float(match.group(1))
                            if 20 < temp < 120:
                                return temp
        except:
            pass
        
        # Способ 3: Intel GPU
        try:
            if os.path.exists('/sys/class/drm/card0/device/hwmon/hwmon0/temp1_input'):
                with open('/sys/class/drm/card0/device/hwmon/hwmon0/temp1_input', 'r') as f:
                    temp = float(f.read().strip()) / 1000.0
                    if 20 < temp < 120:
                        return temp
        except:
            pass
        
        return None
    except Exception as e:
        print(f"Error getting GPU temperature: {e}")
        return None

def get_disk_temperature():
    """Получение температуры диска"""
    try:
        # Способ 1: hddtemp
        try:
            for disk in ['sda', 'sdb', 'sdc', 'sdd']:
                result = subprocess.run(
                    ['hddtemp', '-n', f'/dev/{disk}'], 
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    temp = float(result.stdout.strip())
                    if 20 < temp < 80:
                        print(f"Disk temp from hddtemp /dev/{disk}: {temp}°C")
                        return temp
        except Exception as e:
            print(f"hddtemp error: {e}")
        
        # Способ 2: smartctl
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
        
        # Способ 3: NVMe
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
        
        # Загрузка каждого ядра
        cpu_core_percents = get_cpu_core_usage()
        
        # Температуры
        cpu_temp_value = get_cpu_temperature()
        gpu_temp_value = get_gpu_temperature()
        disk_temp_value = get_disk_temperature()
        
        # Память
        memory = psutil.virtual_memory()
        
        # Диск
        disk = psutil.disk_usage('/')
        
        # Контейнеры
        containers = docker_client.containers.list(all=True)
        running = [c for c in containers if c.status == 'running']
        
        # Обновляем метрики
        cpu_usage_total.set(cpu_percent)
        memory_usage.set(memory.percent)
        memory_used_gb.set(round(memory.used / (1024**3), 1))
        disk_usage_percent.set(disk.percent)
        container_count.set(len(containers))
        container_running.set(len(running))
        
        if cpu_temp_value is not None:
            cpu_temp.set(cpu_temp_value)
        if gpu_temp_value is not None:
            gpu_temp.set(gpu_temp_value)
        if disk_temp_value is not None:
            disk_temp.set(disk_temp_value)
        
        # Результат
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
        
        # Добавляем ядра
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

# Определяем HTML_TEMPLATE
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Docker Container Links & System Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f0f2f5;
        }
        h1 {
            color: #1a1a2e;
            border-bottom: 3px solid #4a90e2;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }
        .system-stats {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 10px;
        }
        .stat-item {
            padding: 12px;
            background: #f8f9fa;
            border-radius: 8px;
            text-align: center;
        }
        .stat-label {
            font-size: 0.8em;
            color: #666;
            margin-bottom: 5px;
        }
        .stat-value {
            font-size: 1.3em;
            font-weight: bold;
            color: #1a1a2e;
        }
        .stat-value.good { color: #4caf50; }
        .stat-value.warning { color: #ff9800; }
        .stat-value.danger { color: #f44336; }
        .stat-bar {
            width: 100%;
            height: 6px;
            background: #e0e0e0;
            border-radius: 3px;
            margin-top: 8px;
            overflow: hidden;
        }
        .stat-bar-fill {
            height: 100%;
            border-radius: 3px;
            transition: width 0.5s ease;
        }
        .stat-bar-fill.good { background: #4caf50; }
        .stat-bar-fill.warning { background: #ff9800; }
        .stat-bar-fill.danger { background: #f44336; }
        .stat-timestamp {
            text-align: right;
            font-size: 0.8em;
            color: #888;
            margin-top: 10px;
        }
        .cpu-cores {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
            gap: 5px;
            margin-top: 10px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .core-item {
            text-align: center;
            padding: 5px;
            background: white;
            border-radius: 5px;
            border: 1px solid #e0e0e0;
        }
        .core-label {
            font-size: 0.7em;
            color: #666;
        }
        .core-value {
            font-size: 1em;
            font-weight: bold;
        }
        .container-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .container-card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: transform 0.2s;
        }
        .container-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        }
        .container-name {
            font-size: 1.2em;
            font-weight: bold;
            color: #1a1a2e;
            margin-bottom: 10px;
        }
        .container-status {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 0.8em;
            margin-bottom: 10px;
        }
        .status-running { background: #4caf50; color: white; }
        .status-exited { background: #f44336; color: white; }
        .port-list { margin: 10px 0; }
        .port-item {
            display: inline-block;
            background: #e8f0fe;
            padding: 5px 12px;
            border-radius: 15px;
            margin: 3px 5px 3px 0;
            font-size: 0.9em;
        }
        .port-link { color: #4a90e2; text-decoration: none; font-weight: 500; }
        .port-link:hover { text-decoration: underline; }
        .no-ports { color: #888; font-style: italic; }
        .container-image { color: #666; font-size: 0.9em; }
        .refresh-btn {
            background: #4a90e2;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 1em;
            margin-bottom: 20px;
        }
        .refresh-btn:hover { background: #357abd; }
        .server-info {
            background: #fff3cd;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            border-left: 4px solid #ffc107;
        }
        .grafana-link {
            background: #e8f0fe;
            padding: 10px 20px;
            border-radius: 5px;
            display: inline-block;
            margin-left: 10px;
        }
        .grafana-link a { color: #4a90e2; text-decoration: none; font-weight: bold; }
        .grafana-link a:hover { text-decoration: underline; }
        @media (max-width: 600px) {
            .stats-grid { grid-template-columns: 1fr 1fr; }
            .container-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <h1>🐳 Docker Container Links & System Monitor</h1>
    
    <div style="margin-bottom: 20px; display: flex; gap: 10px; flex-wrap: wrap;">
        <div class="server-info" style="flex: 1;">
            🌐 Server: <strong>{{ server_ip }}</strong>
        </div>
        <div class="grafana-link">
            📊 <a href="http://{{ server_ip }}:3000" target="_blank">Grafana Dashboard</a>
        </div>
    </div>
    
    <div class="system-stats" id="systemStats">
        <div class="stats-grid" id="statsGrid">
            <div class="stat-item">
                <div class="stat-label">🖥️ CPU Usage</div>
                <div class="stat-value" id="cpuValue">{{ stats.cpu_percent }}%</div>
                <div class="stat-bar">
                    <div class="stat-bar-fill {{ stats.cpu_color }}" id="cpuBar" style="width:{{ stats.cpu_percent }}%"></div>
                </div>
                <div style="font-size:0.8em;color:#888;margin-top:5px;">
                    🌡️ <span id="cpuTemp">{% if stats.cpu_temp %}{{ stats.cpu_temp }}°C{% else %}N/A{% endif %}</span>
                </div>
            </div>
            
            <div class="stat-item">
                <div class="stat-label">🧠 Memory</div>
                <div class="stat-value" id="memoryValue">{{ stats.memory_used }} / {{ stats.memory_total }} GB</div>
                <div class="stat-bar">
                    <div class="stat-bar-fill {{ stats.memory_color }}" id="memoryBar" style="width:{{ stats.memory_percent }}%"></div>
                </div>
            </div>
            
            <div class="stat-item">
                <div class="stat-label">💾 Disk</div>
                <div class="stat-value" id="diskValue">{{ stats.disk_used }} / {{ stats.disk_total }} GB</div>
                <div class="stat-bar">
                    <div class="stat-bar-fill {{ stats.disk_color }}" id="diskBar" style="width:{{ stats.disk_percent }}%"></div>
                </div>
            </div>
            
            <div class="stat-item">
                <div class="stat-label">📦 Containers</div>
                <div class="stat-value" id="containerCount">{{ containers|length }}</div>
                <div style="font-size:0.8em;color:#888;margin-top:5px;">
                    <span id="runningCount">{{ running_count }} running</span>
                </div>
            </div>
        </div>
        
        <div style="margin-top: 15px;">
            <div style="font-size: 0.9em; color: #666; margin-bottom: 5px;">🧩 CPU Cores Usage:</div>
            <div class="cpu-cores" id="cpuCores">
                {% for i in range(cpu_cores_count) %}
                <div class="core-item">
                    <div class="core-label">Core {{ i }}</div>
                    <div class="core-value" id="core_{{ i }}">0%</div>
                </div>
                {% endfor %}
            </div>
        </div>
        
        <div class="stat-timestamp">Updated: <span id="timestamp">{{ stats.timestamp }}</span></div>
    </div>
    
    <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Containers</button>
    
    <div class="container-grid">
        {% for container in containers %}
        <div class="container-card">
            <div class="container-name">{{ container.name }}</div>
            <div>
                <span class="container-status status-{{ container.status }}">{{ container.status }}</span>
            </div>
            <div class="container-image">📦 {{ container.image }}</div>
            <div class="port-list">
                {% if container.ports %}
                    {% for port in container.ports %}
                        <span class="port-item">
                            <a href="http://{{ server_ip }}:{{ port.host_port }}" target="_blank" class="port-link">
                                🌐 {{ port.host_port }} → {{ port.container_port }}/{{ port.type }}
                            </a>
                        </span>
                    {% endfor %}
                {% else %}
                    <span class="no-ports">No exposed ports</span>
                {% endif %}
            </div>
        </div>
        {% endfor %}
    </div>
    <p style="margin-top: 30px; color: #888; font-size: 0.9em;">
        Total containers: {{ containers|length }}
    </p>

    <script>
        function getColorClass(value) {
            if (value < 50) return 'good';
            if (value < 75) return 'warning';
            return 'danger';
        }
        
        function updateStats() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        console.error(data.error);
                        return;
                    }
                    
                    document.getElementById('cpuValue').textContent = data.cpu_percent + '%';
                    const cpuBar = document.getElementById('cpuBar');
                    cpuBar.style.width = data.cpu_percent + '%';
                    cpuBar.className = 'stat-bar-fill ' + getColorClass(data.cpu_percent);
                    
                    const cpuTemp = document.getElementById('cpuTemp');
                    if (data.cpu_temp !== null && data.cpu_temp !== undefined) {
                        cpuTemp.textContent = data.cpu_temp + '°C';
                    } else {
                        cpuTemp.textContent = 'N/A';
                    }
                    
                    document.getElementById('memoryValue').textContent = 
                        data.memory_used + ' / ' + data.memory_total + ' GB';
                    const memoryBar = document.getElementById('memoryBar');
                    memoryBar.style.width = data.memory_percent + '%';
                    memoryBar.className = 'stat-bar-fill ' + getColorClass(data.memory_percent);
                    
                    document.getElementById('diskValue').textContent = 
                        data.disk_used + ' / ' + data.disk_total + ' GB';
                    const diskBar = document.getElementById('diskBar');
                    diskBar.style.width = data.disk_percent + '%';
                    diskBar.className = 'stat-bar-fill ' + getColorClass(data.disk_percent);
                    
                    document.getElementById('timestamp').textContent = data.timestamp;
                    
                    if (data.containers_total !== undefined) {
                        document.getElementById('containerCount').textContent = data.containers_total;
                        document.getElementById('runningCount').textContent = data.containers_running + ' running';
                    }
                    
                    for (let i = 0; i < 64; i++) {
                        const coreElement = document.getElementById('core_' + i);
                        if (coreElement) {
                            const coreKey = 'cpu_core_' + i + '_percent';
                            if (data[coreKey] !== undefined) {
                                coreElement.textContent = data[coreKey] + '%';
                                const color = getColorClass(data[coreKey]);
                                coreElement.style.color = color === 'good' ? '#4caf50' : 
                                                         color === 'warning' ? '#ff9800' : '#f44336';
                            }
                        }
                    }
                })
                .catch(error => console.error('Error fetching stats:', error));
        }
        
        setInterval(updateStats, 1000);
    </script>
</body>
</html>
"""

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