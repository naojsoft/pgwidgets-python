# Examples

## Running

1. Install pgwidgets and its JS dependency:

   ```bash
   pip install -e ../          # pgwidgets (Python bindings)
   pip install pgwidgets-js    # JS/CSS assets (if not already installed)
   ```

2. Run an example script:

   ```bash
   python demo_sync.py
   # or
   python demo_async.py
   ```

3. Open **http://localhost:9501/** in your browser.

   The script prints this URL when it starts.  The built-in HTTP server
   on port 9501 serves the connector page and all JS/CSS assets.  The
   WebSocket server on port 9500 handles the widget protocol.
