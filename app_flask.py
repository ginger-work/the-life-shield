#!/usr/bin/env python3
"""Flask app with proper CORS"""
import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

users = {}

@app.after_request
def after_request(response):
    """Explicitly add CORS headers to every response."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "The Life Shield",
        "version": "1.0.0"
    })

@app.route('/api/v1/auth/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return '', 200
    
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    
    if email in users:
        return jsonify({"error": "User exists"}), 400
    
    users[email] = {
        "id": f"user_{len(users)}",
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "password": password,
    }
    
    return jsonify({
        "success": True,
        "user": {
            "id": users[email]["id"],
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
        },
        "access_token": f"fake-token-{email}",
        "token_type": "bearer"
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
