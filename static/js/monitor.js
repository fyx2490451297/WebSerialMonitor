document.addEventListener('DOMContentLoaded', () => {
    // --- Global state and DOM references ---
    let socket = null;
    const sidebar = document.getElementById('sidebar');
    const portSelect = document.getElementById('port_select');
    const baudrateSelect = document.getElementById('baudrate_select');
    const refreshButton = document.getElementById('refresh_ports_button');
    const connectButton = document.getElementById('connect_button');
    const statusText = document.getElementById('status_text');
    const logDiv = document.getElementById('log');
    const clearLogButton = document.getElementById('clear_log_button');
    const sendInput = document.getElementById('send_input');
    const sendButton = document.getElementById('send_button');
    const rxLed = document.getElementById('rx_led');
    const txLed = document.getElementById('tx_led');
    const timestampToggle = document.getElementById('timestamp_toggle');
    const intervalInput = document.getElementById('interval_input');
    const timedSendToggle = document.getElementById('timed_send_toggle');
    let timedSendTimerId = null;

    // --- UI Update Function ---
    function updateUIForConnection(isConnected) {
        const elementsToDisable = [portSelect, baudrateSelect, refreshButton];
        if (isConnected) {
            connectButton.textContent = 'Close Port';
            connectButton.className = 'connected';
            elementsToDisable.forEach(el => el.disabled = true);
            sendInput.disabled = false;
            sendButton.disabled = false;
            statusText.textContent = `Connected to ${portSelect.value} @ ${baudrateSelect.value} bps`;
        } else {
            connectButton.textContent = 'Open Port';
            connectButton.className = 'disconnected';
            elementsToDisable.forEach(el => el.disabled = false);
            sendInput.disabled = true;
            sendButton.disabled = true;
            statusText.textContent = 'Disconnected';
            if(socket) socket.disconnect();
            socket = null;
        }
    }

    // --- Socket.IO Event Handlers ---
    function setupSocketEventHandlers(_socket) {
        _socket.on('connect', () => updateUIForConnection(true));
        _socket.on('disconnect', () => {
            logToScreen('// Disconnected from server.', 'info');
            if (timedSendToggle.checked) {
                timedSendToggle.checked = false;
                timedSendToggle.dispatchEvent(new Event('change'));
            }
            updateUIForConnection(false);
        });
        _socket.on('serial_data_recv', (msg) => {
            flashLed(rxLed);
            logToScreen(msg.data, 'rx');
        });
        _socket.on('serial_error', (msg) => logToScreen(`Error: ${msg.message}`, 'info'));
        _socket.on('connect_error', (err) => {
            logToScreen(`Connection Error: ${err.message}`, 'info');
            updateUIForConnection(false);
        });
    }

    // --- Main Action Event Listeners ---
    connectButton.addEventListener('click', () => {
        if (connectButton.classList.contains('connected')) {
            updateUIForConnection(false);
        } else {
            const port = portSelect.value;
            if (!port) { alert('Please select a serial port first!'); return; }
            const baudrate = baudrateSelect.value;
            statusText.textContent = `Connecting to ${port}...`;
            socket = io('/serial', { query: { port, baudrate } });
            setupSocketEventHandlers(socket);
        }
    });

    refreshButton.addEventListener('click', async () => {
        const originalText = statusText.textContent;
        statusText.textContent = 'Refreshing port list...';
        try {
            const response = await fetch('/api/list_ports');
            const data = await response.json();
            if (data.success) {
                const currentPort = portSelect.value;
                portSelect.innerHTML = '<option value="">-- Select Port --</option>';
                data.ports.forEach(p => {
                    const option = document.createElement('option');
                    option.value = p; 
                    option.textContent = p;
                    if (p === currentPort) {
                        option.selected = true;
                    }
                    portSelect.appendChild(option);
                });
                statusText.textContent = 'Port list has been refreshed.';
            } else { statusText.textContent = `Refresh failed: ${data.message}`; }
        } catch (error) {
            statusText.textContent = `A network error occurred while refreshing.`;
            console.error('Failed to refresh ports:', error);
        }
        setTimeout(() => { 
            if (statusText.textContent.includes('Refresh')) {
                statusText.textContent = originalText;
            }
        }, 2000);
    });
    
    // --- Helper Functions ---
    function logToScreen(message, type) {
        const isScrolledToBottom = logDiv.scrollHeight - logDiv.clientHeight <= logDiv.scrollTop + 5;
        const line = document.createElement('div');
        line.className = `log-line ${type}`;
        
        if (timestampToggle.checked && type !== 'info') {
            const ts = document.createElement('span');
            ts.className = 'timestamp';
            ts.textContent = '[' + new Date().toLocaleTimeString('en-GB', { hour12: false }) + `.${String(new Date().getMilliseconds()).padStart(3,'0')}` + ']:';
            line.appendChild(ts);
        }
        line.appendChild(document.createTextNode(message));
        logDiv.appendChild(line);
        if (isScrolledToBottom) logDiv.scrollTop = logDiv.scrollHeight;
    }

    clearLogButton.addEventListener('click', () => {
        logDiv.innerHTML = '';
        logToScreen(`// Log cleared at ${new Date().toLocaleTimeString()}`, 'info');
    });

    function sendData() {
        const data = sendInput.value;
        if(data && connectButton.classList.contains('connected')) {
            socket.emit('serial_data_send', {data});
            logToScreen(data, 'tx');
            flashLed(txLed);
        }
    }

    sendButton.addEventListener('click', sendData);
    sendInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); sendData(); }
    });
    
    function flashLed(ledElement) {
        ledElement.classList.add('on');
        setTimeout(() => ledElement.classList.remove('on'), 150);
    }
    
    // --- Timed Send Logic ---
    timedSendToggle.addEventListener('change', function() {
        if (this.checked) {
            const data = sendInput.value;
            const interval = parseInt(intervalInput.value, 10);
            if (!data) {
                alert('Send content cannot be empty!');
                this.checked = false; return;
            }
            if (isNaN(interval) || interval < 100) {
                alert('Interval must be a number greater than or equal to 100!');
                this.checked = false; return;
            }
            timedSendTimerId = setInterval(() => { sendData(data); }, interval);
            sendInput.disabled = true;
            sendButton.disabled = true;
            intervalInput.disabled = true;
            statusText.textContent = `Sending data every ${interval}ms...`;
        } else {
            if (timedSendTimerId) {
                clearInterval(timedSendTimerId);
                timedSendTimerId = null;
            }
            if (connectButton.classList.contains('connected')) {
                sendInput.disabled = false;
                sendButton.disabled = false;
            }
            intervalInput.disabled = false;
            if (socket && socket.connected) {
                statusText.textContent = `Connected to ${portSelect.value} @ ${baudrateSelect.value} bps`;
            } else {
                statusText.textContent = 'Disconnected';
            }
        }
    });
});
