"""Gunicorn config for the flask-multi-process pgwidgets demo.

Run with::

    PGW_BIND_HOST=0.0.0.0 gunicorn -c gunicorn.conf.py server:app

Key constraint — *one worker only*.
======================================

This demo keeps a per-process in-memory registry of
``(session_id, token) -> (port, Process)`` so a returning visitor
(refresh, bookmark, second tab) re-attaches to their *existing*
child process within the idle grace period.

That registry is local to the gunicorn worker that handles the
request.  If we ran multiple workers, each would have an
independent registry — and the moment nginx routed a refresh to
a different worker than the one that spawned the original child,
the demo would silently spawn a duplicate process.

So ``workers = 1`` is not a tuning knob; it's a correctness
requirement.  Concurrency comes from:

  * the worker's thread pool below (``gthread`` + ``threads = N``),
    so multiple HTTP requests can be served at once even though
    one of them is briefly blocked waiting on a child's
    "ready" message; and
  * the per-visitor subprocesses themselves — those do the
    actual pgwidgets work and run independently of the Flask
    layer.

If you need a multi-worker Flask layer, the upgrade path is to
externalise the registry (Redis, SQLite, etc.) so every worker
shares it.  That's a bigger change; see the README.
"""

import os

# ----- Bind ----------------------------------------------------
# Where gunicorn listens for HTTP.  Behind nginx the default
# loopback bind is fine and most secure.
bind = os.environ.get("PGW_GUNICORN_BIND", "127.0.0.1:8000")

# ----- Concurrency --------------------------------------------
# See the docstring — *do not* increase ``workers`` without
# externalising the registry.
workers = 1
worker_class = "gthread"
threads = int(os.environ.get("PGW_GUNICORN_THREADS", "16"))

# Don't ``preload_app``.  Each worker (we only have one) should
# import ``server.py`` itself, so ``multiprocessing.set_start_method``
# runs in the same process that later spawns children.  Preloading
# would run the imports in the gunicorn master and then fork the
# worker — for start_method=spawn it doesn't matter much, but
# avoiding it keeps the model simpler to reason about.
preload_app = False

# ----- Timeouts -----------------------------------------------
# The ``/`` handler waits up to 5 s on a child's ``ready`` message
# (see ``server.py:index``).  The default gunicorn worker timeout
# is 30 s, which already covers that — but bump it a little so a
# slow first-time import (e.g. cold-start of a per-visitor app
# with a heavy import graph) doesn't get the worker killed.
timeout = 60

# Keep gthread workers around long enough to absorb the burst of
# requests when many visitors hit at once.
graceful_timeout = 30
keepalive = 5

# ----- Logging ------------------------------------------------
# Send to stdout/stderr so journald / Docker pick it up naturally.
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("PGW_GUNICORN_LOGLEVEL", "info")
