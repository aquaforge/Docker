#!/usr/bin/env python3
import docker
import socket
import psutil
import logging
import os
from flask import Flask, render_template_string, jsonify, request
from datetime import datetime

app = Flask(__name__)
docker_client = docker.from_env()

# Фильтр для подавления логов /api/stats
class SuppressStatsLogs(logging.Filter):
    def filter(self, record):
        return '/api/stats' not in record.getMessage()

logging.getLogger('werkzeug').addFilter(SuppressStatsLogs())


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

def get_system_stats():
    """Получаем статистику системы"""
    try:
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_freq = psutil.cpu_freq()
        
        # Температура CPU
        cpu_temp = None
        try:
            # Для Linux
            if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    cpu_temp = float(f.read().strip()) / 1000.0
        except:
            pass
        
        # Память
        memory = psutil.virtual_memory()
        
        # Диск
        disk = psutil.disk_usage('/')
        
        return {
            'cpu_percent': round(cpu_percent, 1),
            'cpu_freq': round(cpu_freq.current, 0) if cpu_freq else None,
            'cpu_temp': round(cpu_temp, 1) if cpu_temp else None,
            'memory_used': round(memory.used / (1024**3), 1),
            'memory_total': round(memory.total / (1024**3), 1),
            'memory_percent': memory.percent,
            'disk_used': round(disk.used / (1024**3), 1),
            'disk_total': round(disk.total / (1024**3), 1),
            'disk_percent': disk.percent,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }
    except Exception as e:
        print(f"Stats error: {e}")
        return {
            'error': str(e),
            'cpu_percent': 0,
            'cpu_temp': None,
            'memory_used': 0,
            'memory_total': 0,
            'memory_percent': 0,
            'disk_used': 0,
            'disk_total': 0,
            'disk_percent': 0,
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Docker Container Links & System Monitor</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
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
        
        /* System Stats */
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
        
        /* Containers */
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
        .status-running {
            background: #4caf50;
            color: white;
        }
        .status-exited {
            background: #f44336;
            color: white;
        }
        .port-list {
            margin: 10px 0;
        }
        .port-item {
            display: inline-block;
            background: #e8f0fe;
            padding: 5px 12px;
            border-radius: 15px;
            margin: 3px 5px 3px 0;
            font-size: 0.9em;
        }
        .port-link {
            color: #4a90e2;
            text-decoration: none;
            font-weight: 500;
        }
        .port-link:hover {
            text-decoration: underline;
        }
        .no-ports {
            color: #888;
            font-style: italic;
        }
        .container-image {
            color: #666;
            font-size: 0.9em;
        }
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
        .refresh-btn:hover {
            background: #357abd;
        }
        .server-info {
            background: #fff3cd;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            border-left: 4px solid #ffc107;
        }
        
        @media (max-width: 600px) {
            .stats-grid {
                grid-template-columns: 1fr 1fr;
            }
            .container-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <h1>🐳 Docker Container Links & System Monitor</h1>
    
    <!-- System Stats -->
    <div class="system-stats" id="systemStats">
        <div class="stats-grid" id="statsGrid">
            <!-- CPU -->
            <div class="stat-item">
                <div class="stat-label">🖥️ CPU Usage</div>
                <div class="stat-value" id="cpuValue">{{ stats.cpu_percent }}%</div>
                <div class="stat-bar">
                    <div class="stat-bar-fill {{ stats.cpu_color }}" id="cpuBar" style="width:{{ stats.cpu_percent }}%"></div>
                </div>
                <div style="font-size:0.8em;color:#888;margin-top:5px;">
                    <span id="cpuTemp">{% if stats.cpu_temp %}{{ stats.cpu_temp }}°C{% else %}N/A{% endif %}</span>
                </div>
            </div>
            
            <!-- Memory -->
            <div class="stat-item">
                <div class="stat-label">🧠 Memory</div>
                <div class="stat-value" id="memoryValue">{{ stats.memory_used }} / {{ stats.memory_total }} GB</div>
                <div class="stat-bar">
                    <div class="stat-bar-fill {{ stats.memory_color }}" id="memoryBar" style="width:{{ stats.memory_percent }}%"></div>
                </div>
            </div>
            
            <!-- Disk -->
            <div class="stat-item">
                <div class="stat-label">💾 Disk</div>
                <div class="stat-value" id="diskValue">{{ stats.disk_used }} / {{ stats.disk_total }} GB</div>
                <div class="stat-bar">
                    <div class="stat-bar-fill {{ stats.disk_color }}" id="diskBar" style="width:{{ stats.disk_percent }}%"></div>
                </div>
            </div>
            
            <!-- Containers Count -->
            <div class="stat-item">
                <div class="stat-label">📦 Containers</div>
                <div class="stat-value" id="containerCount">{{ containers|length }}</div>
                <div style="font-size:0.8em;color:#888;margin-top:5px;">
                    <span id="runningCount">{{ running_count }} running</span>
                </div>
            </div>
        </div>
        <div class="stat-timestamp">Updated: <span id="timestamp">{{ stats.timestamp }}</span></div>
    </div>
    
    <div class="server-info">
        🌐 Server: <strong>{{ server_ip }}</strong> (links will use this address)
    </div>
    <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Containers</button>
    
    <!-- Containers List -->
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
                    
                    // CPU
                    document.getElementById('cpuValue').textContent = data.cpu_percent + '%';
                    const cpuBar = document.getElementById('cpuBar');
                    cpuBar.style.width = data.cpu_percent + '%';
                    cpuBar.className = 'stat-bar-fill ' + getColorClass(data.cpu_percent);
                    
                    // CPU Temperature
                    const cpuTemp = document.getElementById('cpuTemp');
                    if (data.cpu_temp !== null && data.cpu_temp !== undefined) {
                        cpuTemp.textContent = data.cpu_temp + '°C';
                    } else {
                        cpuTemp.textContent = 'N/A';
                    }
                    
                    // Memory
                    document.getElementById('memoryValue').textContent = 
                        data.memory_used + ' / ' + data.memory_total + ' GB';
                    const memoryBar = document.getElementById('memoryBar');
                    memoryBar.style.width = data.memory_percent + '%';
                    memoryBar.className = 'stat-bar-fill ' + getColorClass(data.memory_percent);
                    
                    // Disk
                    document.getElementById('diskValue').textContent = 
                        data.disk_used + ' / ' + data.disk_total + ' GB';
                    const diskBar = document.getElementById('diskBar');
                    diskBar.style.width = data.disk_percent + '%';
                    diskBar.className = 'stat-bar-fill ' + getColorClass(data.disk_percent);
                    
                    // Timestamp
                    document.getElementById('timestamp').textContent = data.timestamp;
                })
                .catch(error => console.error('Error fetching stats:', error));
        }
        
        // Обновляем каждую секунду
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
    
    # Получаем статистику для начальной загрузки
    stats = get_system_stats()
    
    # Добавляем цвета для начальной загрузки
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)