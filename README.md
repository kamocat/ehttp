Ehttpserver
===========

Ehttpserver ("Embedded HTTPServer") is a HTTP server library for
CircuitPython. It is a fork of [biplane](https://github.com/Uberi/biplane).

Note that it is _not_ a dropin replacement but contains a number of
incompatible changes. This is the main reason for a fork (besides the fact
that there was no reaction to my pull-requests).

Main changes:

  - **WebSocket protocol support (RFC 6455)** - enables real-time bidirectional
    communication with web clients using the same non-blocking architecture
  - support serving static files (but not automatically below a given root)
  - support pre-compressed files (a request for `foo.html` will return
    the content of `foo.html.gz` instead if it exists).
    Serving jquery-min.js.gz takes only 5 seconds instead of 15 seconds
    and only takes up one third of the flash that the uncompressed file does!
  - paths in routes can be regular expressions
  - request handlers must be methods (need to subclass `ehttpserver.Server`)
  - request handlers have the signature
    `handler(self,path,query_params,headers,body)`
  - moved some of the code to `examples` (e.g. starting AP + webserver)
  - some bugfixes (e.g. biplane prematurely times out on large requests)
  - other code cleanup (e.g. removed multiple `print`-statements)
  - concentrate on CircuitPython. May or may not run with CPython

Otherwise, the main features of biplane are still there (text copied
from the original README.md of Biplane):

Compared to common alternatives such as
[Ampule](https://github.com/deckerego/ampule/),
[circuitpython-native-wsgiserver](https://github.com/Neradoc/circuitpython-native-wsgiserver/), and
 [Adafruit_CircuitPython_HTTPServer](https://github.com/adafruit/Adafruit_CircuitPython_HTTPServer/), it has several unique features:

  - **Non-blocking concurrent I/O**: can process multiple requests
    at the same time, even when `async`/`await`/`asyncio` isn't available!
  - While circuitpython-native-wsgiserver does non-blocking I/O
    as well, it performs certain operations in a blocking loop,
    making soft-realtime use difficult (e.g. displaying animations,
    driving motors).
  - To make this work without `asyncio`,
    we expose the entire server as a generator, where each step of the
    generator is O(1).
  - **More performant**: 10ms per request on a 160MHz ESP32C3,
    thanks to buffered reads/writes and avoiding common issues such as
    bytes concatenation.
  - Comparable to blocking I/O servers such as Ampule and
    Adafruit_CircuitPython_HTTPServer.
  - Much faster than non-blocking I/O servers such as
    circuitpython-native-wsgiserver, which can take up to 100ms per
    request on a 160MHz ESP32C3 due to 1-byte recv() calls.
  - **More robust**: correctly handles binary data, overly-large
    paths/headers/requests, too-slow/dropped connections, etc.
  - Strictly bounds untrusted input size during request processing
    using the `max_request_line_size` and `max_body_bytes` settings.
  - Strictly bounds request processing time using the
    `request_timeout_seconds` setting.
  - Correctly handles unusual cases such as binary data,
    dropped connections with no TCP RST, and incomplete writes from the client.
  - Around the same size as Ampule, and much smaller than the other options
    (on Pico-W: adafruit_httpserver: 46K, ehttpserver: 4.4K)
  - **Few dependencies**: relies only on the `time`, `re` and `errno`
    libraries, both of which are built into CircuitPython
    (as well as `wifi`, `mdns`, and `socketpool` if using the WiFi helpers).

However, compared to those libraries, it intentionally doesn't
include some features in order to keep the codebase small:

  - Helpers for building HTTP responses, such as header formatting,
    templating, and more.
  - Helpers for dealing with MIME types
    (Adafruit_CircuitPython_HTTPServer has this).
  - Support for chunked transfer encoding
    (Adafruit_CircuitPython_HTTPServer has this).


Installation
------------

### CircuitPython

To install Ehttpserver using circup, ensure you have set it up according
to the [Adafruit circup guide](https://learn.adafruit.com/keep-your-circuitpython-libraries-on-devices-up-to-date-with-circup). Then:

    circup install ehttpserver


WebSocket Support
-----------------

Ehttpserver includes optional WebSocket protocol support (RFC 6455) via the
`websocketserver` module, enabling real-time bidirectional communication 
between CircuitPython devices and web clients.

### WebSocket Features

  - **Full RFC 6455 compliance**: Handles handshake, frame parsing, masking, 
    and control frames (ping/pong/close)
  - **Non-blocking I/O**: WebSocket connections use the same generator-based
    non-blocking architecture as HTTP connections
  - **Memory efficient**: Designed for microcontrollers with limited RAM
  - **Easy to use**: Simple decorator-based routing similar to HTTP handlers
  - **Modular design**: WebSocket functionality is in a separate module that
    extends the base Server class

### WebSocket Handler Example

```python
from ehttpserver import Response, route
from websocketserver import WebSocketServer
from websocketserver import WS_OPCODE_TEXT, WS_OPCODE_PING, WS_OPCODE_CLOSE

class MyServer(WebSocketServer):
  @route("/", "GET")
  def serve_page(self, path, query_params, headers, body):
    return Response("<h1>WebSocket Server</h1>", content_type="text/html")
  
  @route("/ws", "WEBSOCKET")
  def handle_websocket(self, path, headers, ws):
    """Echo server - sends back received messages"""
    while not ws.closed:
      # Receive a frame (non-blocking)
      opcode, payload = None, None
      for result in ws.recv_frame():
        yield
        if result:
          opcode, payload = result
      
      if opcode == WS_OPCODE_TEXT:
        message = payload.decode('utf-8')
        yield from ws.send_text(f"Echo: {message}")
      elif opcode == WS_OPCODE_PING:
        yield from ws.send_pong(payload)
      elif opcode == WS_OPCODE_CLOSE:
        yield from ws.send_close()
        break
      
      yield  # Allow other tasks to run
```

### WebSocket Methods

  - `ws.send_text(text)` - Send a text message
  - `ws.send_binary(data)` - Send binary data
  - `ws.send_ping(payload)` - Send a ping frame
  - `ws.send_pong(payload)` - Send a pong response
  - `ws.send_close(code, reason)` - Close the connection
  - `ws.recv_frame()` - Receive the next frame (returns opcode, payload)

### WebSocket Constants

The following opcode constants are exported from `websocketserver`:

  - `WS_OPCODE_CONTINUATION` - Continuation frame (0x0)
  - `WS_OPCODE_TEXT` - Text frame (0x1)
  - `WS_OPCODE_BINARY` - Binary frame (0x2)
  - `WS_OPCODE_CLOSE` - Close frame (0x8)
  - `WS_OPCODE_PING` - Ping frame (0x9)
  - `WS_OPCODE_PONG` - Pong frame (0xA)

### Requirements

WebSocket support requires the `hashlib` and `binascii` modules, which are
included in standard CircuitPython builds. If your board doesn't include
these, WebSocket connections will fail with a RuntimeError.


Examples
--------

A basic example with standard boilerplate-code for CircuitPython is in
`examples/simple_test.py`.

The code in `examples/parallel_test.py` blinks the onboard-LED while
serving requests. With other HTTP servers, blinking the LED while serving
requests would either be impossible, or would become inconsistent when
many HTTP requests are coming in.

A WebSocket echo server example with a browser-based test page is in
`examples/websocket_test.py`. This demonstrates real-time bidirectional
communication between a web browser and the CircuitPython device.

Note that CircuitPython's GC pauses may cause occasional longer pauses
To mitigate this, run `import gc; gc.collect()` at regular, predictable
intervals, so that the GC never has to be invoked at unpredictable times.

An alternative with `asyncio` (not available on all boards) is in
`examples/asyncio_test.py`. Essentially, we just need to loop through
the generator as usual while calling `await asyncio.sleep(0)` each iteration
to let other tasks run.

A full scale real life example is part of
<https://github.com/bablokb/pcb-pico-datalogger>. That project provides
a web-based administration interface and serves big files (e.g. jquery)
and provides an API for browsers.


Development
-----------

All of the application code lives in `ehttpserver.py`.


License
-------

Copyright 2023 bablokb@gmx.de
Copyright 2023 [Anthony Zhang (Uberi)](http://anthonyz.ca).

The source code is available online at
[GitHub](https://github.com/bablokb/circuitpython-ehttpserver).

Based on _biplane_ from [GitHub](https://github.com/Uberi/biplane).

This program is made available under the MIT license. See ``LICENSE.txt``
in the project's root directory for more information.
