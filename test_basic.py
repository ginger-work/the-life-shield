#!/usr/bin/env python3
"""Most basic possible app"""
import os

def app(environ, start_response):
    status = '200 OK'
    response_headers = [('Content-type', 'application/json')]
    start_response(status, response_headers)
    return [b'{"status":"ok"}']

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting on port {port}...")
    serve(app, host='0.0.0.0', port=port)
