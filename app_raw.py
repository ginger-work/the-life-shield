#!/usr/bin/env python3
"""Raw WSGI app - no frameworks"""
import os
import json

users = {}
tokens = {}  # token -> {user_id, email}

CORS_HEADERS = [
    ('Access-Control-Allow-Origin', '*'),
    ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
    ('Access-Control-Allow-Headers', 'Content-Type, Authorization'),
]

def app(environ, start_response):
    path = environ['PATH_INFO']
    method = environ['REQUEST_METHOD']
    
    print(f"[{method}] {path}", flush=True)  # Debug logging
    
    # Handle CORS preflight for ANY path
    if method == 'OPTIONS':
        start_response('200 OK', [('Content-Type', 'application/json')] + CORS_HEADERS)
        return [b'{}']
    
    if path == '/health' and method == 'GET':
        start_response('200 OK', [('Content-Type', 'application/json')] + CORS_HEADERS)
        return [json.dumps({"status": "healthy", "service": "The Life Shield", "version": "1.0.0"}).encode()]
    
    elif '/api/v1/auth/register' in path and method == 'POST':
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
            
            import secrets as _secrets
            user_id = f"usr_{_secrets.token_urlsafe(8)}"
            users[email] = {
                "id": user_id,
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "password": password,
                "role": "client",
            }
            
            access_token = _secrets.token_urlsafe(32)
            refresh_token = _secrets.token_urlsafe(32)
            tokens[access_token] = {"user_id": user_id, "email": email}
            tokens[refresh_token] = {"user_id": user_id, "email": email}
            
            start_response('200 OK', [('Content-Type', 'application/json')] + CORS_HEADERS)
            return [json.dumps({
                "success": True,
                "user": {
                    "id": user_id,
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                },
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": 86400,
                "user_id": user_id,
                "role": "client",
            }).encode()]
        except Exception as e:
            start_response('500 Internal Server Error', [('Content-Type', 'application/json')] + CORS_HEADERS)
            return [json.dumps({"error": str(e)}).encode()]
    
    elif '/api/v1/auth/login' in path and method == 'POST':
        try:
            content_len = int(environ.get('CONTENT_LENGTH', 0))
            body = environ['wsgi.input'].read(content_len).decode('utf-8')
            data = json.loads(body)
            
            email = (data.get('email') or '').strip().lower()
            password = data.get('password', '')
            
            if email not in users:
                start_response('401 Unauthorized', [('Content-Type', 'application/json')] + CORS_HEADERS)
                return [json.dumps({"error": "Invalid email or password", "code": "INVALID_CREDENTIALS"}).encode()]
            
            user = users[email]
            if user['password'] != password:
                start_response('401 Unauthorized', [('Content-Type', 'application/json')] + CORS_HEADERS)
                return [json.dumps({"error": "Invalid email or password", "code": "INVALID_CREDENTIALS"}).encode()]
            
            import secrets as _secrets
            access_token = _secrets.token_urlsafe(32)
            refresh_token = _secrets.token_urlsafe(32)
            tokens[access_token] = {"user_id": user["id"], "email": email}
            tokens[refresh_token] = {"user_id": user["id"], "email": email}
            
            start_response('200 OK', [('Content-Type', 'application/json')] + CORS_HEADERS)
            return [json.dumps({
                "success": True,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": 86400,
                "user_id": user["id"],
                "role": user.get("role", "client"),
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "first_name": user.get("first_name", ""),
                    "last_name": user.get("last_name", ""),
                },
            }).encode()]
        except Exception as e:
            start_response('500 Internal Server Error', [('Content-Type', 'application/json')] + CORS_HEADERS)
            return [json.dumps({"error": str(e)}).encode()]
    
    elif '/api/v1/auth/me' in path and method == 'GET':
        auth_header = environ.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            start_response('401 Unauthorized', [('Content-Type', 'application/json')] + CORS_HEADERS)
            return [json.dumps({"error": "Unauthorized"}).encode()]
        token = auth_header[7:]
        if token not in tokens:
            # Legacy fake-token support
            for email, user in users.items():
                if token == f"fake-token-{email}":
                    start_response('200 OK', [('Content-Type', 'application/json')] + CORS_HEADERS)
                    return [json.dumps(user).encode()]
            start_response('401 Unauthorized', [('Content-Type', 'application/json')] + CORS_HEADERS)
            return [json.dumps({"error": "Invalid token"}).encode()]
        token_data = tokens[token]
        user = users.get(token_data['email'], {})
        start_response('200 OK', [('Content-Type', 'application/json')] + CORS_HEADERS)
        return [json.dumps({
            "id": user.get("id"),
            "email": user.get("email"),
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "role": user.get("role", "client"),
        }).encode()]
    
    elif '/api/v1/auth/logout' in path and method == 'POST':
        auth_header = environ.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            tokens.pop(token, None)
        start_response('200 OK', [('Content-Type', 'application/json')] + CORS_HEADERS)
        return [json.dumps({"success": True}).encode()]
    
    else:
        start_response('404 Not Found', [('Content-Type', 'application/json')] + CORS_HEADERS)
        return [json.dumps({"error": "Not found"}).encode()]

if __name__ == '__main__':
    from wsgiref.simple_server import make_server
    port = int(os.environ.get('PORT', 8000))
    print(f"Starting on port {port}...")
    httpd = make_server('0.0.0.0', port, app)
    httpd.serve_forever()
