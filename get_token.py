#!/usr/bin/env python3
"""
Authenticate with Beeper Desktop API via OAuth2 PKCE.
Saves the access token to .beeper_token in the current directory.

Usage:
    python get_token.py
"""

import argparse
import base64
import hashlib
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

parser = argparse.ArgumentParser(description="Get Beeper Desktop API access token")
parser.add_argument("--port", type=int, default=19876, help="Local callback port (default: 19876)")
parser.add_argument("--beeper-url", default="http://localhost:23373", help="Beeper Desktop API base URL")
args = parser.parse_args()

BEEPER_BASE = args.beeper_url
REDIRECT_URI = f"http://localhost:{args.port}/callback"
CLIENT_ID = "beeper-export"

code_verifier = secrets.token_urlsafe(64)
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b"=").decode()
state = secrets.token_urlsafe(32)

auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authorized! You can close this tab.</h1>")
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<h1>Error: {params.get('error', ['unknown'])[0]}</h1>".encode())

    def log_message(self, format, *args):
        pass


auth_url = (
    f"{BEEPER_BASE}/oauth/authorize?"
    + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "read",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
)

print("Opening browser for Beeper authorization...")
print(f"If it doesn't open, visit:\n  {auth_url}\n")
webbrowser.open(auth_url)

server = HTTPServer(("localhost", args.port), CallbackHandler)
print("Waiting for authorization...")
server.handle_request()
server.server_close()

if not auth_code:
    print("ERROR: No authorization code received.")
    raise SystemExit(1)

resp = requests.post(
    f"{BEEPER_BASE}/oauth/token",
    data={
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier,
    },
)

if resp.status_code != 200:
    print(f"ERROR: Token exchange failed ({resp.status_code}): {resp.text}")
    raise SystemExit(1)

token = resp.json().get("access_token")
with open(".beeper_token", "w") as f:
    f.write(token)

print("Token saved to .beeper_token")
