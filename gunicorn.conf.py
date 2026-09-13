"""
Gunicorn configuration for PHINOX production.

Loaded via ``gunicorn config.wsgi:application --config gunicorn.conf.py``
(see ``docker/Dockerfile`` CMD and ``docker/docker-compose.yml`` web service).

Tuning notes
------------
- ``workers`` defaults to ``cpu_count() * 2 + 1`` (Gunicorn's documented
  general-purpose recommendation). For I/O-bound Django views this leaves
  plenty of headroom; tune per-deployment if needed.
- ``worker_class = "sync"`` is the safest default for Django + sessions +
  CSRF. Switch to ``gevent`` only after auditing DB connection pooling and
  third-party libs for monkey-patching side effects.
- ``preload_app = True`` trades slightly slower worker boot for lower
  per-worker memory (code is loaded once in the master, then copy-on-write
  shared) — appropriate on a small (1–2 vCPU) box where RSS matters.
- ``max_requests`` + ``max_requests_jitter`` recycle workers periodically
  to mitigate any slow memory leaks in third-party libs.
"""
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
max_requests = 1000
max_requests_jitter = 50
timeout = 30
keepalive = 5
loglevel = "info"
accesslog = "-"
errorlog = "-"
preload_app = True

# Graceful shutdown — give in-flight requests up to 30s to finish before
# the worker is force-killed (e.g. on `docker stop` / rolling deploy).
graceful_timeout = 30
