import multiprocessing
import os

# 服务器 socket
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
backlog = 2048

# Worker 进程
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
timeout = 60
graceful_timeout = 30
keepalive = 2

# 服务器机制
daemon = False
raw_env = []
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# 日志
errorlog = "-"
loglevel = "info"
accesslog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 进程命名
proc_name = "async_blog"

# 服务器钩子
def when_ready(server):
    server.log.info("Server is ready. Spawning workers")

def worker_int(worker):
    worker.log.info("worker received INT or QUIT signal")

def pre_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_exec(server):
    server.log.info("Forked child, re-executing.")

def on_starting(server):
    server.log.info("Starting server...")

def on_reload(server):
    server.log.info("Reloading server...")

def worker_abort(worker):
    worker.log.info("Worker aborted (pid: %s)", worker.pid)

def on_exit(server):
    server.log.info("Shutting down server...")
