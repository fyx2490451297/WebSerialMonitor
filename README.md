<h1>Web Serial Monitor</h1>

![SerialMonitor!](/assets/images/SerialMonitor.png)

A lightweight, modern, and powerful web-based serial monitor designed for remote debugging and team collaboration.

[Read this document in Chinese](README.CN.md)

The Core Problem It Solves
Have you ever encountered these scenarios?

Test equipment is located in a dedicated server room or lab that is inconvenient to access frequently.

Hardware engineers are operating on-site, while software engineers need to view debug logs remotely from the office.

Team members are in different locations but need to observe the real-time output of the same serial device simultaneously.

You don't want to configure a complex set of serial drivers and debugging tools on every team member's computer.

Web Serial Monitor is built to solve these pain points. It uses a server-client (C/S) architecture. You only need to run this application on a server that has physical access to the serial devices. Then, anyone on your team can securely access and operate these serial ports in real-time from anywhere, using just a web browser. This dramatically improves the efficiency of remote work and team collaboration.

✨ Features
Remote Real-time Access: Monitor and control physical serial ports on a remote server in real-time through a web browser.

Modern Single-Page Application (SPA): All operations are performed on a single interface without page reloads, providing a smooth user experience.

Multi-Client Support: Multiple users can connect to and monitor the output of the same serial port simultaneously.

Dynamic Port and Baud Rate Selection: Freely select from available serial ports and common baud rates before connecting.

Live Port List Refresh: Discover newly plugged-in serial devices dynamically without restarting the server or refreshing the page.

Bi-directional Communication: Supports sending data from the web interface to the serial port and displaying data received from the port in real-time.

Rich UI Feedback:

Clear connection status display.

RX/TX indicator LEDs for intuitive feedback on data activity.

Optional timestamps for easy log tracing and analysis.

Color-coded display for sent (TX) and received (RX) data.

One-click log clearing.

Modular Code Structure: The project codebase is carefully refactored for clarity, maintainability, and ease of extension.

Companion Testing Tools:

Includes a virtual_device.py script to simulate a serial device, facilitating full testing without physical hardware.

Includes a python_client.py script to demonstrate programmatic interaction with the service, useful for automation and integration.

🛠️ Tech Stack
Backend: Python, Flask, Flask-SocketIO, pyserial-asyncio, eventlet

Frontend: HTML5, CSS3 (Flexbox), Vanilla JavaScript

Real-time Communication: WebSocket (via Socket.IO)

🚀 Installation and Usage
1. Clone or Download the Project

git clone [Your Project Repository URL]
cd WebSerialMonitor

2. Create and Activate a Python Virtual Environment (Recommended)

# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate

3. Install All Dependencies

All project dependencies are listed in the requirements.txt file.

pip install -r requirements.txt

4. Run the Main Application

Make sure your terminal is in the project's root directory.

python app.py

After the service starts, you will see output similar to the following, indicating the server is running on http://0.0.0.0:50002.

INFO:werkzeug: * Running on http://0.0.0.0:50002
(Press CTRL+C to quit)

5. Access the Web Interface

Open your web browser (Chrome or Firefox recommended) and navigate to http://localhost:50002.

📖 How to Use
Web Interface
Select Parameters: In the left sidebar, choose the desired Serial Port and Baud Rate from the dropdown menus.

Refresh Ports: If you plug in a new serial device after the page has loaded, click the "Refresh" button to update the port list.

Connect: Click the blue "Open Port" button. Upon successful connection, the button will turn into a red "Close Port" button, the settings in the sidebar will be locked, and the sending controls in the main area will be activated.

Send and Receive Data:

Data received from the serial port will be displayed in the log area in real-time.

Enter the data you want to send in the input field at the bottom and press Enter or click the "Send" button.

Disconnect: Click the red "Close Port" button to safely disconnect. All controls will reset to their initial state.

Using the Testing Tools (Optional)
If you don't have a physical serial device on hand, you can use the provided scripts for testing.

Create a Virtual Serial Port Pair:

Windows: Install and use a tool like com0com to create a virtual COM port pair (e.g., COM16 and COM17).

Linux/macOS: Use socat. Run socat -d -d pty,raw,echo=0 pty,raw,echo=0 in a terminal. It will output two available pseudo-terminal paths (e.g., /dev/pts/3 and /dev/pts/4).

Run the Virtual Device:
Open a second terminal, run virtual_device.py, and point it to one of the virtual ports.

# Example using COM16
python virtual_device.py COM16 --baudrate 115200

This script will simulate a device that periodically sends data.

Connect from the Web Interface:
In the web interface, select the other port from the virtual pair (e.g., COM17) and click "Open Port". You should now see the data sent by the virtual device.

📜 License
This project is licensed under the MIT License. You are free to use, modify, and distribute the code.