"""
Minimal WebSocket Echo Server Example

This demonstrates the simplest possible WebSocket server:
- Connects to WiFi
- Accepts WebSocket connections at ws://device-ip/echo
- Echoes back any text messages received
"""

import gc
import wifi
import socketpool
from ehttpserver import Response, route
from websocketserver import WebSocketServer, WS_OPCODE_TEXT, WS_OPCODE_CLOSE

# WiFi credentials
WIFI_SSID = "your-wifi-ssid"
WIFI_PASSWORD = "your-wifi-password"

class MinimalWebSocketServer(WebSocketServer):
    
    @route("/", "GET")
    def serve_homepage(self, path, query_params, headers, body):
        """Serve a minimal HTML page with WebSocket client"""
        html = """<!DOCTYPE html>
<html><body>
<h1>Minimal Echo Test</h1>
<input id="i" type="text"><button onclick="ws.send(i.value)">Send</button>
<div id="log"></div>
<script>
const ws = new WebSocket('ws://' + location.host + '/echo');
ws.onmessage = e => {
  const p = document.createElement('p');
  p.textContent = e.data;
  log.appendChild(p);
};
</script>
</body></html>"""
        return Response(html, content_type="text/html")
    
    @route("/echo", "WEBSOCKET")
    def handle_echo(self, path, headers, ws):
        """Echo any received text back to the client"""
        while not ws.closed:
            opcode, payload = None, None
            
            # Receive frame (non-blocking via generator)
            for result in ws.recv_frame():
                yield
                if result:
                    opcode, payload = result
            
            # Echo text messages
            if opcode == WS_OPCODE_TEXT:
                yield from ws.send_text(payload.decode('utf-8'))
            elif opcode == WS_OPCODE_CLOSE:
                yield from ws.send_close()
                break
            
            yield  # Let other connections run

# Connect to WiFi
print(f"Connecting to {WIFI_SSID}...")
wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
print(f"Connected! IP: {wifi.radio.ipv4_address}")

# Start server
pool = socketpool.SocketPool(wifi.radio)
server = MinimalWebSocketServer(debug=True)

print(f"WebSocket server running at http://{wifi.radio.ipv4_address}:80")
print("Open the URL in a browser to test")

with pool.socket() as server_socket:
    for _ in server.start(server_socket, listen_on=('0.0.0.0', 80)):
        gc.collect()
