#!/usr/bin/env python3
"""
GLC Study Bot server.
- Serves static files (index.html, login.html)
- Password-protects the app via session cookie
- Proxies Anthropic API calls using server-side API key

Environment variables (set in Render dashboard):
  ANTHROPIC_API_KEY  — your Anthropic API key
  SITE_PASSWORD      — the class password students enter
  PORT               — port to listen on (set automatically by Render)
"""
import os
import secrets
import urllib.request
import urllib.error
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
SITE_PASSWORD     = os.environ.get('SITE_PASSWORD', 'GLC')
PORT              = int(os.environ.get('PORT', 8083))

_sessions = set()  # active session tokens (in-memory)


class Handler(SimpleHTTPRequestHandler):

    # ── GET ──────────────────────────────────────────────────────────
    def do_GET(self):
        # Protect the main app
        if self.path in ('/', '/index.html'):
            if not self._authed():
                self._redirect('/login.html')
                return
        super().do_GET()

    # ── POST ─────────────────────────────────────────────────────────
    def do_POST(self):
        if self.path == '/login':
            self._handle_login()
        elif self.path == '/api/messages':
            if not self._authed():
                self.send_response(401)
                self.end_headers()
                return
            self._proxy_api()
        else:
            self.send_response(404)
            self.end_headers()

    # ── OPTIONS (CORS preflight) ──────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    # ── Auth helpers ─────────────────────────────────────────────────
    def _authed(self):
        for part in self.headers.get('Cookie', '').split(';'):
            part = part.strip()
            if part.startswith('glc_session=') and part[12:] in _sessions:
                return True
        return False

    def _handle_login(self):
        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n).decode()
        password = parse_qs(body).get('password', [''])[0]
        if password == SITE_PASSWORD:
            token = secrets.token_hex(32)
            _sessions.add(token)
            self.send_response(302)
            self.send_header('Location', '/')
            self.send_header('Set-Cookie',
                f'glc_session={token}; Path=/; HttpOnly; SameSite=Lax')
            self.end_headers()
        else:
            self._redirect('/login.html?error=1')

    def _redirect(self, url):
        self.send_response(302)
        self.send_header('Location', url)
        self.end_headers()

    # ── API proxy ────────────────────────────────────────────────────
    def _proxy_api(self):
        n = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(n)
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=body,
            headers={
                'x-api-key': ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                resp = r.read()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors_headers()
            self.end_headers()
            self.wfile.write(resp)
        except urllib.error.HTTPError as e:
            err = e.read()
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self._cors_headers()
            self.end_headers()
            self.wfile.write(err)

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, fmt, *args):
        pass  # suppress request logs


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    httpd = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'GLC Study Bot running → http://localhost:{PORT}')
    httpd.serve_forever()
