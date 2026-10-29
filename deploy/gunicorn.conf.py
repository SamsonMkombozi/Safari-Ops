# gunicorn -c deploy/gunicorn.conf.py config.wsgi
import multiprocessing
import os

bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8010')
workers = int(os.environ.get('WEB_CONCURRENCY', min(4, multiprocessing.cpu_count() * 2 + 1)))
threads = 2
timeout = 60
graceful_timeout = 30
max_requests = 1000          # recycle workers to cap memory growth
max_requests_jitter = 100
accesslog = '-'
errorlog = '-'
forwarded_allow_ips = '127.0.0.1'
