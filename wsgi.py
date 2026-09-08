"""Adapt the existing classroom handlers to a production WSGI server.

No request is parsed twice: Gunicorn parses HTTP and this adapter provides
the normalized headers/body to the shared application handlers.
"""
import io
from email.message import Message
from http import HTTPStatus
from server import Handler

class WSGIHandler(Handler):
    def __init__(self, environ):
        self.command = environ['REQUEST_METHOD']
        self.path = environ.get('PATH_INFO', '/')
        if environ.get('QUERY_STRING'):
            self.path += '?' + environ['QUERY_STRING']
        self.headers = Message()
        for key, value in environ.items():
            if key.startswith('HTTP_'):
                self.headers[key[5:].replace('_', '-')] = value
        for key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            if environ.get(key):
                self.headers[key.replace('_', '-')] = environ[key]
        self.rfile = environ['wsgi.input']
        self.wfile = io.BytesIO()
        self.status = 200
        self.response_headers = []

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, name, value):
        self.response_headers.append((name, str(value)))

    def end_headers(self):
        pass

def application(environ, start_response):
    handler = WSGIHandler(environ)
    try:
        if handler.command in ('GET', 'HEAD'):
            handler.do_GET()
        elif handler.command == 'POST':
            handler.do_POST()
        else:
            handler.send({'error': 'Method not allowed'}, 405)
    except Exception:
        handler.wfile = io.BytesIO()
        handler.response_headers = []
        handler.send({'error': 'ระบบไม่พร้อม กรุณาลองใหม่'}, 500)
    handler.response_headers.append(('X-Frame-Options','DENY'))
    start_response(f'{handler.status} {HTTPStatus(handler.status).phrase}', handler.response_headers)
    return [b'' if handler.command == 'HEAD' else handler.wfile.getvalue()]
