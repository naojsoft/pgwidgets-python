Using an External Web Server
============================

The built-in HTTP server is convenient for development, but for
production deployments an external web server can provide better
security, performance, and flexibility -- TLS termination, static file
caching, load balancing, access control, and integration with existing
infrastructure.

The pgwidgets architecture makes this straightforward. The built-in
HTTP server does only two things:

1. Serves the pgwidgets JavaScript/CSS static files.
2. Serves ``remote.html`` with the WebSocket URL injected.

An external web server replaces both of these responsibilities while
the Python process continues to run the WebSocket server.


Setup Overview
--------------

1. Disable the built-in HTTP server:

   .. code-block:: python

      app = Application(http_server=False)

2. Serve the pgwidgets static files from your external server. The path
   to the static files can be obtained programmatically:

   .. code-block:: python

      from pgwidgets.sync import Application

      app = Application(http_server=False)
      print("Static files:", app.static_path)
      print("Remote HTML:", app.remote_html)

3. Inject the WebSocket URL into the HTML page so the browser knows
   where to connect. There are two ways:

   - Set ``window.PGWIDGETS_WS_URL`` in a ``<script>`` tag before the
     module script runs.
   - Pass the URL as a query parameter: ``?ws=ws://your-host:9500``

4. If using TLS, use ``wss://`` instead of ``ws://`` for the WebSocket
   URL.


nginx
-----

nginx serves the static files and reverse-proxies the WebSocket
connection to the Python process.

**nginx configuration:**

.. code-block:: nginx

   server {
       listen 80;
       server_name myapp.example.com;

       # Serve pgwidgets static files.
       # Set this to the output of app.static_path
       root /path/to/pgwidgets/static;

       # Serve remote.html at / with the WebSocket URL injected.
       location = / {
           sub_filter '<head>' '<head>\n<script>window.PGWIDGETS_WS_URL = "ws://$host/ws";</script>';
           sub_filter_once on;
           try_files /remote.html =404;
       }

       # Reverse-proxy WebSocket connections to the Python server.
       location /ws {
           proxy_pass http://127.0.0.1:9500;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_read_timeout 86400s;
           proxy_send_timeout 86400s;
       }
   }

**Python side:**

.. code-block:: python

   from pgwidgets.sync import Application

   app = Application(http_server=False, host="127.0.0.1", ws_port=9500)

   @app.on_connect
   def on_session(session):
       Widgets = session.get_widgets()
       top = Widgets.TopLevel(title="nginx Demo", resizable=True)
       # ... build UI ...
       top.show()

   app.run()

**With TLS:**

.. code-block:: nginx

   server {
       listen 443 ssl;
       server_name myapp.example.com;

       ssl_certificate /etc/letsencrypt/live/myapp.example.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/myapp.example.com/privkey.pem;

       root /path/to/pgwidgets/static;

       location = / {
           sub_filter '<head>' '<head>\n<script>window.PGWIDGETS_WS_URL = "wss://$host/ws";</script>';
           sub_filter_once on;
           try_files /remote.html =404;
       }

       location /ws {
           proxy_pass http://127.0.0.1:9500;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_read_timeout 86400s;
           proxy_send_timeout 86400s;
       }
   }

Note the use of ``wss://`` in the injected script when serving over
HTTPS.


FastAPI
-------

FastAPI is built on ASGI and runs on an asyncio event loop, so it works
with both the sync and async versions of pgwidgets. The async version
is a more natural fit since both share the same event loop.

**Async version (recommended):**

The async pgwidgets Application can be started alongside FastAPI using
a lifespan handler, with no threading required:

.. code-block:: python

   import asyncio
   from contextlib import asynccontextmanager
   from fastapi import FastAPI
   from fastapi.staticfiles import StaticFiles
   from fastapi.responses import HTMLResponse
   from pgwidgets.async_ import Application

   pgapp = Application(http_server=False, host="127.0.0.1", ws_port=9500)

   @pgapp.on_connect
   async def on_session(session):
       Widgets = session.get_widgets()
       top = await Widgets.TopLevel(title="FastAPI Async Demo", resizable=True)
       await top.resize(400, 300)
       label = await Widgets.Label("Hello from FastAPI + pgwidgets!")
       vbox = await Widgets.VBox(spacing=8, padding=10)
       await vbox.add_widget(label, 1)
       await top.set_widget(vbox)
       await top.show()

   @asynccontextmanager
   async def lifespan(app):
       # Start the pgwidgets WebSocket server on the shared event loop
       task = asyncio.create_task(pgapp.start())
       yield
       task.cancel()

   web = FastAPI(lifespan=lifespan)

   @web.get("/", response_class=HTMLResponse)
   async def index():
       html = pgapp.remote_html.read_text(encoding="utf-8")
       inject = '<script>window.PGWIDGETS_WS_URL = "ws://localhost:9500";</script>\n'
       return html.replace("<head>", "<head>\n" + inject, 1)

   # Serve pgwidgets JS/CSS assets
   web.mount("/", StaticFiles(directory=str(pgapp.static_path)), name="static")

**Sync version:**

The sync Application runs its own event loop, so it needs a background
thread:

.. code-block:: python

   import threading
   from fastapi import FastAPI
   from fastapi.staticfiles import StaticFiles
   from fastapi.responses import HTMLResponse
   from pgwidgets.sync import Application

   pgapp = Application(http_server=False, host="127.0.0.1", ws_port=9500)

   @pgapp.on_connect
   def on_session(session):
       Widgets = session.get_widgets()
       top = Widgets.TopLevel(title="FastAPI Sync Demo", resizable=True)
       top.resize(400, 300)
       label = Widgets.Label("Hello from FastAPI + pgwidgets!")
       vbox = Widgets.VBox(spacing=8, padding=10)
       vbox.add_widget(label, 1)
       top.set_widget(vbox)
       top.show()

   # Start pgwidgets in a background thread
   threading.Thread(target=pgapp.run, daemon=True).start()

   web = FastAPI()

   @web.get("/", response_class=HTMLResponse)
   def index():
       html = pgapp.remote_html.read_text(encoding="utf-8")
       inject = '<script>window.PGWIDGETS_WS_URL = "ws://localhost:9500";</script>\n'
       return html.replace("<head>", "<head>\n" + inject, 1)

   # Serve pgwidgets JS/CSS assets
   web.mount("/", StaticFiles(directory=str(pgapp.static_path)), name="static")

**Running either version:**

.. code-block:: bash

   uvicorn myapp:web --host 0.0.0.0 --port 8000

Then open ``http://localhost:8000`` in a browser. FastAPI serves the
HTML and static assets on port 8000, while the pgwidgets WebSocket
server runs on port 9500.


Flask
-----

.. code-block:: python

   from flask import Flask, send_from_directory
   from pgwidgets.sync import Application
   import threading

   pgapp = Application(http_server=False, host="127.0.0.1", ws_port=9500)

   @pgapp.on_connect
   def on_session(session):
       Widgets = session.get_widgets()
       top = Widgets.TopLevel(title="Flask Demo", resizable=True)
       top.resize(400, 300)
       label = Widgets.Label("Hello from Flask + pgwidgets!")
       vbox = Widgets.VBox(spacing=8, padding=10)
       vbox.add_widget(label, 1)
       top.set_widget(vbox)
       top.show()

   threading.Thread(target=pgapp.run, daemon=True).start()

   web = Flask(__name__, static_folder=str(pgapp.static_path), static_url_path="")

   @web.route("/")
   def index():
       html = pgapp.remote_html.read_text(encoding="utf-8")
       inject = '<script>window.PGWIDGETS_WS_URL = "ws://localhost:9500";</script>\n'
       return html.replace("<head>", "<head>\n" + inject, 1)

   if __name__ == "__main__":
       web.run(host="0.0.0.0", port=8000)


Apache
------

Apache can serve static files and reverse-proxy WebSocket connections
using ``mod_proxy`` and ``mod_proxy_wstunnel``.

**Enable required modules:**

.. code-block:: bash

   a2enmod proxy proxy_http proxy_wstunnel rewrite substitute

**Apache virtual host configuration:**

.. code-block:: apache

   <VirtualHost *:80>
       ServerName myapp.example.com

       # Serve pgwidgets static files
       DocumentRoot /path/to/pgwidgets/static

       # Inject WebSocket URL into remote.html
       <Location "/">
           AddOutputFilterByType SUBSTITUTE text/html
           Substitute "s|<head>|<head>\n<script>window.PGWIDGETS_WS_URL = \"ws://myapp.example.com/ws\";</script>|i"
       </Location>

       # Reverse-proxy WebSocket
       ProxyPass "/ws" "ws://127.0.0.1:9500/"
       ProxyPassReverse "/ws" "ws://127.0.0.1:9500/"

       # Direct requests for / to remote.html
       RewriteEngine On
       RewriteRule ^/$ /remote.html [L]
   </VirtualHost>


Caddy
-----

`Caddy <https://caddyserver.com>`_ provides automatic HTTPS and a
simple configuration syntax.

**Caddyfile:**

.. code-block:: text

   myapp.example.com {
       root * /path/to/pgwidgets/static

       # Serve remote.html at / with WebSocket URL injected
       handle / {
           rewrite * /remote.html
           file_server
       }

       # Reverse-proxy WebSocket connections
       handle /ws {
           reverse_proxy 127.0.0.1:9500
       }

       # Serve static files
       handle {
           file_server
       }
   }

With Caddy, TLS is automatic -- it obtains and renews certificates via
Let's Encrypt. The browser page needs to use ``wss://`` for the
WebSocket URL when served over HTTPS. You can inject it by using
Caddy's ``templates`` directive, or by passing it as a query parameter
(``https://myapp.example.com/?ws=wss://myapp.example.com/ws``).


Security Considerations
-----------------------

When deploying with an external web server:

- **Use TLS** -- serve over HTTPS and use ``wss://`` for the WebSocket
  connection.  The internal development server does not support TLS;
  an external server provides this.
- **Bind the WebSocket server to localhost** -- use
  ``host="127.0.0.1"`` so the WebSocket port is not directly exposed.
  Let the external server reverse-proxy to it.
- **Restrict access** -- use the external server's authentication and
  access control features to limit who can reach the application.
- **Set timeouts** -- configure appropriate proxy timeouts for
  long-lived WebSocket connections (the examples above use 86400s /
  24 hours for nginx).
