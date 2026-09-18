#!/usr/bin/env python3
"""
web_service.py -- Servicio web de normalización de mensajes.

Recibe un mensaje de texto y devuelve la versión normalizada:
elimina espacios en blanco repetidos, dejando un solo espacio entre palabras.

Uso:
    python3 web/web_service.py

El servicio escucha en http://localhost:8000 por defecto.
"""

import re
import json
from http.server import HTTPServer, BaseHTTPRequestHandler


WEB_PORT = 8000


def normalize_message(text):

    """Elimina espacios repetidos, deja un solo espacio entre palabras."""
    return re.sub(r'\s+', ' ', text).strip()


class NormalizationHandler(BaseHTTPRequestHandler):
    """Manejador HTTP para la normalización de mensajes."""

    def do_POST(self):
        if self.path == '/normalize':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                data = json.loads(body.decode('utf-8'))
                msg = data.get('message', '')
                normalized = normalize_message(msg)
                response = json.dumps({'message': normalized}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(response)))
                self.end_headers()
                self.wfile.write(response)
            except Exception:
                self.send_response(400)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        # Silenciar logs del servidor por defecto
        pass


if __name__ == '__main__':
    server = HTTPServer(('localhost', WEB_PORT), NormalizationHandler)
    print(f'Web service listening on http://localhost:{WEB_PORT}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nWeb service stopped.')
        server.server_close()
