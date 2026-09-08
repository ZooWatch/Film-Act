import os

bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
# One process preserves the shared SQLite transaction lock. Do not increase.
workers = 1
worker_class = 'gthread'
threads = 8
timeout = 60
graceful_timeout = 30
keepalive = 5
errorlog = '-'
# Do not log request URLs or student data.
accesslog = None
limit_request_line = 4094
limit_request_fields = 50
limit_request_field_size = 8190
