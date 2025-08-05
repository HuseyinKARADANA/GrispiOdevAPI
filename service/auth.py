from functools import wraps
from flask import request, jsonify
import jwt
import os
from dotenv import load_dotenv

SECRET_KEY = os.getenv("SECRET_KEY")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split(" ")
            if len(parts) == 2 and parts[0] == "Bearer":
                token = parts[1]
                print(token)

        if not token:
            return jsonify({'error': 'Token gerekli!'}), 401

        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.user = data  # Tüm user data'sını set et
            request.user_id = data['id']  # ID'yi de ayrıca set et
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token süresi dolmuş!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Geçersiz token!'}), 401

        return f(*args, **kwargs)
    return decorated