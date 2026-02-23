import gc
import wifi
import mdns
import socketpool

from ehttpserver import Response, route
from websocketserver import WebSocketServer, WS_OPCODE_TEXT, WS_OPCODE_CLOSE, WS_OPCODE_PING

class MyWebSocketServer(WebSocketServer):

  # --- HTTP handler for root   ---------------------------------------------

  @route("/","GET")
  def _handle_main(self,path,query_params, headers, body):
    """ Serve a simple WebSocket test page """
    html = """<!DOCTYPE html>
<html>
<head><title>WebSocket Test</title></head>
<body>
  <h1>WebSocket Echo Test</h1>
  <div id="status">Connecting...</div>
  <input id="msg" type="text" placeholder="Type a message">
  <button onclick="send()">Send</button>
  <div id="log"></div>
  <script>
    const ws = new WebSocket('ws://' + location.host + '/ws');
    const status = document.getElementById('status');
    const log = document.getElementById('log');
    
    ws.onopen = () => {
      status.textContent = 'Connected';
      status.style.color = 'green';
    };
    
    ws.onmessage = (e) => {
      const p = document.createElement('p');
      p.textContent = 'Received: ' + e.data;
      log.appendChild(p);
    };
    
    ws.onclose = () => {
      status.textContent = 'Disconnected';
      status.style.color = 'red';
    };
    
    function send() {
      const msg = document.getElementById('msg').value;
      ws.send(msg);
      document.getElementById('msg').value = '';
    }
  </script>
</body>
</html>"""
    return Response(html, content_type="text/html")

  # --- WebSocket handler for /ws   -----------------------------------------

  @route("/ws","WEBSOCKET")
  def _handle_websocket(self, path, headers, ws):
    """ WebSocket echo handler - echoes back any text message received """
    
    self.debug(f"WebSocket connection opened for {path}")
    
    try:
      while not ws.closed:
        # Receive a frame
        opcode, payload = None, None
        for result in ws.recv_frame():
          yield
          if result:
            opcode, payload = result
        
        if opcode is None:
          # Connection closed by client
          break
        
        # Handle different frame types
        if opcode == WS_OPCODE_TEXT:
          # Echo text message back
          message = payload.decode('utf-8', errors='replace')
          self.debug(f"Received: {message}")
          echo_msg = f"Echo: {message}"
          yield from ws.send_text(echo_msg)
          
        elif opcode == WS_OPCODE_PING:
          # Respond to ping with pong
          self.debug("Received ping")
          yield from ws.send_pong(payload)
          
        elif opcode == WS_OPCODE_CLOSE:
          # Client initiated close
          self.debug("Client closed connection")
          yield from ws.send_close()
          break
        
        # Allow other tasks to run
        yield
        
    except Exception as e:
      self.debug(f"WebSocket error: {e}")
      try:
        yield from ws.send_close(1011, "Server error")
      except:
        pass
    
    self.debug("WebSocket connection closed")

  # --- start AP   ---------------------------------------------------------

  def start_ap(self):
    """ start AP-mode """
    wifi.radio.stop_station()
    try:
      wifi.radio.start_ap(ssid="ws_test",password="websocket123")
    except NotImplementedError:
      # workaround for older CircuitPython versions
      pass

  # --- run server   -------------------------------------------------------

  def run_server(self):
    server = mdns.Server(wifi.radio)
    server.hostname = "wstest"
    server.advertise_service(service_type="_http",
                             protocol="_tcp", port=80)
    pool = socketpool.SocketPool(wifi.radio)
    print(f"starting {server.hostname}.local ({wifi.radio.ipv4_address_ap})")
    with pool.socket() as server_socket:
      yield from self.start(server_socket)

  # --- run AP and server   ------------------------------------------------

  def run(self):
    """ start AP and then run server """
    self.start_ap()
    started = False
    for _ in self.run_server():
      if not started:
        print(f"WebSocket server listening on http://{wifi.radio.ipv4_address_ap}:80")
        print(f"Connect to WiFi 'ws_test' (password: websocket123)")
        print(f"Then open http://{wifi.radio.ipv4_address_ap} in your browser")
        started = True
      gc.collect()

# Run the server with debug output
wsserver = MyWebSocketServer(debug=True)
wsserver.run()
