"""
WebSocket Server Extension for ehttpserver

This module provides WebSocket protocol support (RFC 6455) for the ehttpserver
CircuitPython HTTP server. It extends the base Server class with WebSocket
upgrade handling and frame processing.

Usage:
    from websocketserver import WebSocketServer, route
    from websocketserver import WS_OPCODE_TEXT, WS_OPCODE_CLOSE, WS_OPCODE_PING
    
    class MyServer(WebSocketServer):
        @route("/ws", "WEBSOCKET")
        def handle_ws(self, path, headers, ws):
            while not ws.closed:
                opcode, payload = None, None
                for result in ws.recv_frame():
                    yield
                    if result:
                        opcode, payload = result
                
                if opcode == WS_OPCODE_TEXT:
                    yield from ws.send_text(payload.decode('utf-8'))
                elif opcode == WS_OPCODE_CLOSE:
                    yield from ws.send_close()
                    break
                yield
"""

import re
try:
  import hashlib
  import binascii
except ImportError:
  # Fallback for minimal CircuitPython builds
  hashlib = None
  binascii = None

from ehttpserver import Server, Response

__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/bablokb/ehttpserver.git"

# WebSocket protocol constants
_WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# WebSocket opcodes (exported for use in handlers)
WS_OPCODE_CONTINUATION = 0x0
WS_OPCODE_TEXT = 0x1
WS_OPCODE_BINARY = 0x2
WS_OPCODE_CLOSE = 0x8
WS_OPCODE_PING = 0x9
WS_OPCODE_PONG = 0xA

def _ws_make_accept_key(client_key):
  """Generate Sec-WebSocket-Accept header value from client key"""
  if not hashlib or not binascii:
    raise RuntimeError("WebSocket requires hashlib and binascii modules")
  sha1 = hashlib.sha1()
  sha1.update(client_key.encode('ascii') if isinstance(client_key, str) else client_key)
  sha1.update(_WS_GUID)
  return binascii.b2a_base64(sha1.digest()).strip().decode('ascii')


class WebSocketConnection:
  """WebSocket connection handler for CircuitPython non-blocking architecture"""
  
  def __init__(self, buffered_socket):
    self.buffered_socket = buffered_socket
    self.closed = False
    
  def send_frame(self, opcode, payload):
    """Send a WebSocket frame (generator for non-blocking)"""
    frame = bytearray()
    # First byte: FIN=1, RSV=0, opcode
    frame.append(0x80 | (opcode & 0x0F))
    
    # Second byte and payload length
    payload_len = len(payload)
    if payload_len < 126:
      frame.append(payload_len)
    elif payload_len < 65536:
      frame.append(126)
      frame.append((payload_len >> 8) & 0xFF)
      frame.append(payload_len & 0xFF)
    else:
      frame.append(127)
      for i in range(7, -1, -1):
        frame.append((payload_len >> (8 * i)) & 0xFF)
    
    # Send frame header + payload
    yield from self.buffered_socket.write(frame + payload)
  
  def send_text(self, text):
    """Send text message (generator)"""
    payload = text.encode('utf-8') if isinstance(text, str) else text
    yield from self.send_frame(WS_OPCODE_TEXT, payload)
  
  def send_binary(self, data):
    """Send binary message (generator)"""
    yield from self.send_frame(WS_OPCODE_BINARY, data)
  
  def send_pong(self, payload=b""):
    """Send pong response (generator)"""
    yield from self.send_frame(WS_OPCODE_PONG, payload)
  
  def send_close(self, code=1000, reason=""):
    """Send close frame (generator)"""
    payload = bytearray()
    if code is not None:
      payload.append((code >> 8) & 0xFF)
      payload.append(code & 0xFF)
      if reason:
        payload.extend(reason.encode('utf-8')[:123])  # Max 125 bytes total
    yield from self.send_frame(WS_OPCODE_CLOSE, payload)
    self.closed = True
  
  def recv_frame(self):
    """Receive and parse a WebSocket frame (generator)
    
    Yields during I/O, returns (opcode, payload) when complete
    """
    # Read first 2 bytes
    header = bytearray()
    for data in self.buffered_socket.read(size=2):
      yield
      header.extend(data)
      if len(header) >= 2:
        break
    
    if len(header) < 2:
      return None, None  # Connection closed
    
    b1, b2 = header[0], header[1]
    fin = (b1 >> 7) & 1
    opcode = b1 & 0x0F
    masked = (b2 >> 7) & 1
    payload_len = b2 & 0x7F
    
    # Read extended payload length if needed
    if payload_len == 126:
      len_bytes = bytearray()
      for data in self.buffered_socket.read(size=2):
        yield
        len_bytes.extend(data)
        if len(len_bytes) >= 2:
          break
      payload_len = (len_bytes[0] << 8) | len_bytes[1]
    elif payload_len == 127:
      len_bytes = bytearray()
      for data in self.buffered_socket.read(size=8):
        yield
        len_bytes.extend(data)
        if len(len_bytes) >= 8:
          break
      payload_len = 0
      for b in len_bytes:
        payload_len = (payload_len << 8) | b
    
    # Read masking key if present
    mask_key = None
    if masked:
      mask_key = bytearray()
      for data in self.buffered_socket.read(size=4):
        yield
        mask_key.extend(data)
        if len(mask_key) >= 4:
          break
    
    # Read payload
    payload = bytearray()
    if payload_len > 0:
      for data in self.buffered_socket.read(size=payload_len):
        yield
        payload.extend(data)
        if len(payload) >= payload_len:
          break
    
    # Unmask payload if needed
    if masked and mask_key:
      for i in range(len(payload)):
        payload[i] ^= mask_key[i % 4]
    
    return opcode, bytes(payload)


class WebSocketServer(Server):
  """
  HTTP Server with WebSocket protocol support.
  
  Extends the base Server class to handle WebSocket upgrade requests
  and manage WebSocket connections using the same non-blocking generator
  architecture.
  
  To create a WebSocket handler, use the @route decorator with "WEBSOCKET"
  as the method:
  
      @route("/ws", "WEBSOCKET")
      def handle_websocket(self, path, headers, ws):
          while not ws.closed:
              opcode, payload = None, None
              for result in ws.recv_frame():
                  yield
                  if result:
                      opcode, payload = result
              
              if opcode == WS_OPCODE_TEXT:
                  yield from ws.send_text(payload.decode('utf-8'))
              elif opcode == WS_OPCODE_CLOSE:
                  yield from ws.send_close()
                  break
              yield
  """
  
  def _handle_websocket_upgrade(self, headers, buffered_client_socket):
    """Handle WebSocket upgrade handshake and return WebSocketConnection"""
    
    # Validate WebSocket handshake headers
    ws_key = headers.get('sec-websocket-key')
    if not ws_key:
      yield from Response("Bad Request", 400).serialize()
      return None
    
    upgrade = headers.get('upgrade', '').lower()
    connection = headers.get('connection', '').lower()
    
    if upgrade != 'websocket' or 'upgrade' not in connection:
      yield from Response("Bad Request", 400).serialize()
      return None
    
    # Generate accept key
    try:
      accept_key = _ws_make_accept_key(ws_key)
    except Exception as e:
      self.debug(f"WebSocket handshake failed: {e}")
      yield from Response("Internal Server Error", 500).serialize()
      return None
    
    # Send upgrade response
    response = (
      b"HTTP/1.1 101 Switching Protocols\r\n"
      b"Upgrade: websocket\r\n"
      b"Connection: Upgrade\r\n"
      b"Sec-WebSocket-Accept: " + accept_key.encode('ascii') + b"\r\n"
      b"\r\n"
    )
    
    for _ in buffered_client_socket.write(response):
      yield
    
    self.debug("WebSocket handshake complete")
    return WebSocketConnection(buffered_client_socket)

  def _handle_request(self, target, method, headers, content_length,
                      buffered_client_socket):
    """
    Override _handle_request to intercept WebSocket upgrade requests.
    
    If the request is a WebSocket upgrade, handles the handshake and
    dispatches to the appropriate WEBSOCKET route handler. Otherwise,
    delegates to the parent class HTTP handler.
    """
    
    self.debug(f"_handle_request for {target}")
    
    # Check for WebSocket upgrade
    if (headers.get('upgrade', '').lower() == 'websocket' and 
        method == 'GET'):
      ws_conn = None
      for result in self._handle_websocket_upgrade(headers, buffered_client_socket):
        yield
        if isinstance(result, WebSocketConnection):
          ws_conn = result
      
      if ws_conn:
        # Extract path for routing
        path = target.split("?", 1)[0] if "?" in target else target
        
        # Find matching WebSocket handler
        for route_path, route_method, request_handler in self.routes:
          if route_method == 'WEBSOCKET' and re.match(route_path, path):
            yield from request_handler(self, path, headers, ws_conn)
            return
        
        # No handler found, close connection
        self.debug("No WebSocket handler found")
        yield from ws_conn.send_close()
      return
    
    # Not a WebSocket request, delegate to parent class
    yield from super()._handle_request(target, method, headers, 
                                       content_length, buffered_client_socket)
