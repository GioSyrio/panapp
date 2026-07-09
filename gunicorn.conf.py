import os

# ── Gunicorn config for Panapp ──
# Run: gunicorn app:app

# Worker config
workers = 4                        # 2 × CPU cores (2 vCPU for small instance)
worker_class = "sync"
threads = 2
timeout = 120                       # Allow long AI responses
keepalive = 5

# Preload: loads the app once and forks workers (faster, shared caches)
preload_app = True

# Binding
bind = f"0.0.0.0:{os.environ.get('PORT', 5050)}"

# Logging
accesslog = "-"                     # stdout
errorlog = "-"                      # stderr
loglevel = "info"

# Process naming
proc_name = "panapp"

# Graceful shutdown
graceful_timeout = 30
max_requests = 1000                # Recycle workers periodically
max_requests_jitter = 200