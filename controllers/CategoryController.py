from flask import Blueprint, request, jsonify
from service.auth import token_required
import pyodbc
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

category_controller = Blueprint('category_controller', __name__)
CONNECTION_STRING = os.getenv("CONNECTION_STRING")


@category_controller.route('/add', methods=['POST'])
@token_required
def add_category():
    try:
        data = request.get_json()
        category_name = data.get('category_name')

        if not category_name:
            return jsonify({'error': 'category_name gerekli'}), 400

        created_at = datetime.now()
        is_active = 1

        with pyodbc.connect(CONNECTION_STRING) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO TblCategory (category_name, is_active, created_at)
                VALUES (?, ?, ?)
            """, (category_name, is_active, created_at))
            conn.commit()

        return jsonify({'message': 'Kategori başarıyla eklendi'}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@category_controller.route('/list', methods=['GET'])
@token_required
def list_categories():
    try:
        with pyodbc.connect(CONNECTION_STRING) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, category_name, is_active, created_at 
                FROM TblCategory
                ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()

            result = []
            for row in rows:
                result.append({
                    'id': row.id,
                    'category_name': row.category_name,
                    'is_active': bool(row.is_active),
                    'created_at': str(row.created_at)
                })

        return jsonify(result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@category_controller.route('/active_list', methods=['GET'])
@token_required
def list_active_categories():
    try:
        with pyodbc.connect(CONNECTION_STRING) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, category_name, is_active, created_at 
                FROM TblCategory
                WHERE is_active = 1
                ORDER BY category_name ASC
            """)
            rows = cursor.fetchall()

            result = []
            for row in rows:
                result.append({
                    'id': row.id,
                    'category_name': row.category_name,
                    'is_active': bool(row.is_active),
                    'created_at': str(row.created_at)
                })

        return jsonify(result), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@category_controller.route('/update/<int:category_id>', methods=['PUT'])
@token_required
def update_category(category_id):
    try:
        data = request.get_json()
        category_name = data.get('category_name')
        is_active = data.get('is_active')

        if category_name is None or is_active is None:
            return jsonify({'error': 'Eksik veri'}), 400

        with pyodbc.connect(CONNECTION_STRING) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE TblCategory
                SET category_name = ?, is_active = ?
                WHERE id = ?
            """, (category_name, is_active, category_id))
            conn.commit()

        return jsonify({'message': 'Kategori güncellendi'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@category_controller.route('/delete/<int:category_id>', methods=['DELETE'])
@token_required
def delete_category(category_id):
    try:
        with pyodbc.connect(CONNECTION_STRING) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM TblCategory WHERE id = ?", (category_id,))
            conn.commit()

        return jsonify({'message': 'Kategori silindi'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
