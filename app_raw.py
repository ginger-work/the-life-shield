#!/usr/bin/env python3
"""Raw WSGI app - no frameworks"""
import os
import json

users = {}

CORS_HEADERS = [
    ('Access-Control-Allow-Origin', '*'),
    ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
    ('Access-Control-Allow-Headers', 'Content-Type, Authorization'),
]

def app(environ, start_response):
    path = environ['PATH_INFO']
    method = environ['REQUEST_METHOD']
    
    # Handle CORS preflight
    if method == 'OPTIONS':
        start_response('200 OK', [('Content-Type', 'application/json')] + CORS_HEADERS)
        return [b'{}']
    
    if path == '/health' and method == 'GET':
        start_response('200 OK', [('Content-Type', 'application/json')] + CORS_HEADERS)
        return [json.dumps({"status": "healthy", "service": "The Life Shield", "version": "1.0.0"}).encode()]
    
    elif path == '/api/v1/auth/register' and method == 'POST':
        try:
            content_len = int(environ.get('CONTENT_LENGTH', 0))
            body = environ['wsgi.input'].read(content_len).decode('utf-8')
            data = json.loads(body)
            
            email = data.get('email')
            password = data.get('password')
            first_name = data.get('first_name')
            last_name = data.get('last_name')
            
            if email in users:
                start_response('400 Bad Request', [('Content-Type', 'application/json')] + CORS_HEADERS)
                return [json.dumps({"error": "User exists"}).encode()]
            
            users[email] = {
                "id": f"user_{len(users)}",
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "password": password,
            }
            
            start_response('200 OK', [('Content-Type', 'application/json')] + CORS_HEADERS)
            return [json.dumps({
                "success": True,
                "user": {
                    "id": users[email]["id"],
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                },
                "access_token": "fake-token-" + email,
                "token_type": "bearer"
            }).encode()]
        except Exception as e:
            start_response('500 Internal Server Error', [('Content-Type', 'application/json')] + CORS_HEADERS)
            return [json.dumps({"error": str(e)}).encode()]
    
    else:
        start_response('404 Not Found', [('Content-Type', 'application/json')] + CORS_HEADERS)
        return [json.dumps({"error": "Not found"}).encode()]

if __name__ == '__main__':
    from wsgiref.simple_server import make_server
    port = int(os.environ.get('PORT', 8000))
    print(f"Starting on port {port}...")
    httpd = make_server('0.0.0.0', port, app)
    httpd.serve_forever()
