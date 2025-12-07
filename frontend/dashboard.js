/**
 * EKAIA Puerto - Dashboard JavaScript
 * Real-time vehicle tracking interface
 */

class Dashboard {
    constructor() {
        this.ws = null;
        this.reconnectInterval = 5000;
        this.isConnected = false;
        this.latestPlates = { entrada: null, salida: null };

        this.init();
    }

    init() {
        this.setupWebSocket();
        this.setupStreamMonitoring();
        this.updateTimestamp();
        setInterval(() => this.updateTimestamp(), 1000);
    }

    setupWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/realtime`;

        console.log('Connecting to:', wsUrl);

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('✅ WebSocket connected');
            this.isConnected = true;
            this.updateConnectionStatus(true);
            this.addLog('Conectado al servidor');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleRealtimeUpdate(data);
            } catch (e) {
                console.error('Error parsing WebSocket data:', e);
            }
        };

        this.ws.onerror = (error) => {
            console.error('❌ WebSocket error:', error);
            this.updateConnectionStatus(false);
        };

        this.ws.onclose = () => {
            console.log('🔌 WebSocket disconnected');
            this.isConnected = false;
            this.updateConnectionStatus(false);
            this.addLog('Desconectado del servidor. Reintentando...');

            // Reconnect
            setTimeout(() => this.setupWebSocket(), this.reconnectInterval);
        };
    }

    handleRealtimeUpdate(data) {
        console.log('📥 Update received:', data);

        // Update stats
        if (data.stats) {
            this.updateStats(data.stats);
        }

        // Update camera status
        if (data.cameras) {
            this.updateCameraStatus(data.cameras);
        }
    }

    updateStats(stats) {
        document.getElementById('vehicles-inside').textContent = stats.vehicles_inside || 0;
        document.getElementById('exits-today').textContent = stats.exits_today || 0;
        document.getElementById('avg-duration').textContent = `${stats.avg_duration_minutes || 0} min`;

        // Update vehicles table
        this.updateVehiclesTable(stats.current_vehicles || []);
    }

    updateCameraStatus(cameras) {
        let activeCount = 0;

        // Entrada
        const entradaStatus = document.getElementById('entrada-status');
        const entradaInfo = document.getElementById('entrada-info');

        if (cameras.entrada && cameras.entrada.connected) {
            entradaStatus.classList.add('active');
            entradaStatus.classList.remove('inactive');
            activeCount++;

            const plates = cameras.entrada.plates || [];
            if (plates.length > 0) {
                const latest = plates[0];
                entradaInfo.textContent = `✅ Detectado: ${latest.text} (${(latest.confidence * 100).toFixed(0)}%)`;
                this.showLatestPlate(latest.text, 'entrada');
                this.addLog(`🚗 Entrada: ${latest.text}`, 'entry');

                // Update latest
                this.latestPlates.entrada = latest.text;
            } else {
                entradaInfo.textContent = `✅ Stream activo - ${cameras.entrada.detections_count || 0} detecciones`;
            }
        } else {
            entradaStatus.classList.add('inactive');
            entradaStatus.classList.remove('active');
            entradaInfo.textContent = '❌ Stream desconectado';
        }

        // Salida
        const salidaStatus = document.getElementById('salida-status');
        const salidaInfo = document.getElementById('salida-info');

        if (cameras.salida && cameras.salida.connected) {
            salidaStatus.classList.add('active');
            salidaStatus.classList.remove('inactive');
            activeCount++;

            const plates = cameras.salida.plates || [];
            if (plates.length > 0) {
                const latest = plates[0];
                salidaInfo.textContent = `✅ Detectado: ${latest.text} (${(latest.confidence * 100).toFixed(0)}%)`;
                this.showLatestPlate(latest.text, 'salida');
                this.addLog(`📤 Salida: ${latest.text}`, 'exit');

                // Update latest
                this.latestPlates.salida = latest.text;
            } else {
                salidaInfo.textContent = `✅ Stream activo - ${cameras.salida.detections_count || 0} detecciones`;
            }
        } else {
            salidaStatus.classList.add('inactive');
            salidaStatus.classList.remove('active');
            salidaInfo.textContent = '❌ Stream desconectado';
        }

        document.getElementById('cameras-active').textContent = `${activeCount}/2`;
    }

    updateVehiclesTable(vehicles) {
        const tbody = document.getElementById('vehicles-tbody');

        if (vehicles.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No hay vehículos en el puerto</td></tr>';
            return;
        }

        tbody.innerHTML = vehicles.map(v => {
            const entryTime = new Date(v.entry_time).toLocaleTimeString('es-CL');
            const duration = this.calculateDuration(v.entry_time);

            return `
                <tr>
                    <td><strong>${v.plate}</strong></td>
                    <td>${entryTime}</td>
                    <td>${duration}</td>
                    <td><span class="status-inside">Dentro</span></td>
                </tr>
            `;
        }).join('');
    }

    calculateDuration(entryTime) {
        const now = new Date();
        const entry = new Date(entryTime);
        const diffMs = now - entry;
        const diffMins = Math.floor(diffMs / 60000);

        if (diffMins < 60) {
            return `${diffMins} min`;
        } else {
            const hours = Math.floor(diffMins / 60);
            const mins = diffMins % 60;
            return `${hours}h ${mins}min`;
        }
    }

    showLatestPlate(plate, camera) {
        const display = document.querySelector('.plate-display');
        const plateText = display.querySelector('.plate-text');
        const plateMeta = display.querySelector('.plate-meta');

        plateText.textContent = plate;
        plateMeta.textContent = `${camera === 'entrada' ? 'Entrada' : 'Salida'} - ${new Date().toLocaleTimeString('es-CL')}`;

        // Animation
        display.style.transform = 'scale(1.05)';
        setTimeout(() => {
            display.style.transform = 'scale(1)';
        }, 200);
    }

    addLog(message, type = '') {
        const logContainer = document.getElementById('activity-log');
        const entry = document.createElement('div');
        entry.className = `log-entry ${type}`;

        const timestamp = new Date().toLocaleTimeString('es-CL');
        entry.innerHTML = `<span class="log-timestamp">[${timestamp}]</span> ${message}`;

        logContainer.insertBefore(entry, logContainer.firstChild);

        // Keep last 50 entries
        while (logContainer.children.length > 50) {
            logContainer.removeChild(logContainer.lastChild);
        }
    }

    updateConnectionStatus(connected) {
        const badge = document.getElementById('connection-status');
        if (connected) {
            badge.textContent = 'Conectado';
            badge.classList.add('connected');
            badge.classList.remove('disconnected');
        } else {
            badge.textContent = 'Desconectado';
            badge.classList.add('disconnected');
            badge.classList.remove('connected');
        }
    }

    updateTimestamp() {
        const now = new Date();
        document.getElementById('timestamp').textContent = now.toLocaleString('es-CL');
    }

    setupStreamMonitoring() {
        // Monitor stream images for errors
        const streams = ['stream-entrada', 'stream-salida'];

        streams.forEach(id => {
            const img = document.getElementById(id);

            img.onerror = () => {
                console.warn(`⚠️ Stream ${id} error`);
                // Retry after 5 seconds
                setTimeout(() => {
                    img.src = img.src.split('?')[0] + '?t=' + Date.now();
                }, 5000);
            };

            img.onload = () => {
                console.log(`✅ Stream ${id} loaded`);
            };
        });
    }
}

// Initialize dashboard when page loads
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 EKAIA Dashboard initialized');
    window.dashboard = new Dashboard();
});
