from flask import Blueprint, request, jsonify
import pyodbc
import jwt
import datetime
import bcrypt
import os
from dotenv import load_dotenv
from service.auth import token_required
from service.aes_service import AESService

# .env dosyasını yükle
load_dotenv()
# SMTP bilgilerini çek

user_controller = Blueprint('user_controller', __name__)

SECRET_KEY = os.getenv("SECRET_KEY")


CONNECTION_STRING = os.getenv("CONNECTION_STRING")



@user_controller.route('/register', methods=['POST'])
def register_user():
    try:
        data = request.get_json()
        print("Gelen JSON:", data)

        # Gerekli alanları kontrol et
        required_fields = ['name', 'surname', 'preliminary_phone', 'preliminary_email', 'password', 'role']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Gerekli alanlar eksik"}), 400

        # Verileri al
        name = data['name']
        surname = data['surname']
        preliminary_phone = data['preliminary_phone']
        preliminary_email = data['preliminary_email']
        password = data['password'].encode('utf-8')
        role = data['role']

        # AES ile şifreleme
        enc_name = AESService.encrypt(name)
        enc_surname = AESService.encrypt(surname)
        enc_phone = AESService.encrypt(preliminary_phone)
        enc_email = AESService.encrypt(preliminary_email)
        enc_role = AESService.encrypt(role)

        # Şifre hashle → AES ile şifrele
        hashed_password = bcrypt.hashpw(password, bcrypt.gensalt()).decode('utf-8')
        enc_password = AESService.encrypt(hashed_password)

        with pyodbc.connect(CONNECTION_STRING) as db:
            cursor = db.cursor()

            # Aynı e-posta (şifrelenmiş haliyle) zaten var mı?
            cursor.execute("SELECT COUNT(*) FROM TblUser WHERE preliminary_email = ?", (enc_email,))
            if cursor.fetchone()[0] > 0:
                return jsonify({"error": "Bu e-posta zaten kayıtlı!"}), 400

            # INSERT işlemi
            cursor.execute("""
                INSERT INTO TblUser (name, surname, preliminary_phone, preliminary_email, password, role, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
            """, (enc_name, enc_surname, enc_phone, enc_email, enc_password, enc_role, 1))

        return jsonify({"message": "Kullanıcı başarıyla eklendi!"}), 200

    except KeyError as e:
        print(f"KeyError: {e}")
        return jsonify({"error": f"Eksik alan: {str(e)}"}), 400
    except pyodbc.Error as e:
        print(f"Veritabanı Hatası: {e}")
        return jsonify({"error": "Veritabanı hatası oluştu."}), 500
    except Exception as e:
        print(f"Genel Hata: {e}")
        return jsonify({"error": "Sunucu hatası oluştu."}), 500


@user_controller.route('/login', methods=['POST'])
def login():
    """Mail ve şifre ile giriş yapar."""
    try:
        data = request.get_json()
        print("📥 Gelen JSON:", data)

        if not all(k in data for k in ('email', 'password')):
            return jsonify({"error": "Gerekli alanlar eksik"}), 400

        email = data['email']
        password = data['password'].encode('utf-8')
        rememberMe = data.get('rememberMe', False)

        # AES ile email'i şifrele
        encrypted_email = AESService.encrypt(email)

        with pyodbc.connect(CONNECTION_STRING) as db:
            cursor = db.cursor()
            cursor.execute("""
                SELECT id, name, surname, password, role
                FROM TblUser 
                WHERE preliminary_email = ? AND is_active = 1
            """, (encrypted_email,))
            result = cursor.fetchone()

        if result:
            user_id, enc_name, enc_surname, enc_password, enc_role = result

            # Şifreyi AES ile çöz, sonra bcrypt ile karşılaştır
            decrypted_password = AESService.decrypt(enc_password)
            if bcrypt.checkpw(password, decrypted_password.encode('utf-8')):

                # Kullanıcı bilgilerini AES ile çöz
                name = AESService.decrypt(enc_name)
                surname = AESService.decrypt(enc_surname)
                role = AESService.decrypt(enc_role)
                expire_time = datetime.timedelta(days=7) if rememberMe else datetime.timedelta(hours=8)
                exp = datetime.datetime.utcnow() + expire_time

                payload = {
                    "id": user_id,
                    "name": name,
                    "surname": surname,
                    "email": email,
                    "role": role,
                    "exp": int(exp.timestamp())
                }

                token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

                return jsonify({
                    "message": "Giriş başarılı!",
                    "token": token
                }), 200
            else:
                return jsonify({"error": "Geçersiz e-posta veya şifre"}), 401
        else:
            return jsonify({"error": "Geçersiz e-posta veya şifre"}), 401

    except pyodbc.Error as e:
        print(f"🚨 MSSQL Hatası: {e}")
        return jsonify({"error": "Veritabanı hatası"}), 500
    except Exception as e:
        print(f"🚨 Genel Hata: {e}")
        return jsonify({"error": "Dahili Sunucu Hatası"}), 500


@user_controller.route('/profile', methods=['GET'])
@token_required
def get_user_profile():
    try:
        user_id = request.user_id

        with pyodbc.connect(CONNECTION_STRING) as conn:
            cursor = conn.cursor()

            # Kullanıcı bilgilerini çek
            cursor.execute("""
                SELECT name, surname, preliminary_phone, preliminary_email, website, profile_img, role
                FROM TblUser
                WHERE id = ? AND is_active = 1
            """, (user_id,))
            user_row = cursor.fetchone()

            if not user_row:
                return jsonify({'error': 'Kullanıcı bulunamadı'}), 404

            # Adres bilgilerini çek
            cursor.execute("""
                SELECT country, city, address_line, postal_code
                FROM TblAddress
                WHERE user_id = ? AND is_active = 1
            """, (user_id,))
            address_row = cursor.fetchone()

            # AES ile çöz
            profile_data = {
                "name": AESService.decrypt(user_row.name),
                "surname": AESService.decrypt(user_row.surname),
                "preliminary_phone": AESService.decrypt(user_row.preliminary_phone),
                "preliminary_email": AESService.decrypt(user_row.preliminary_email),
                "website": AESService.decrypt(user_row.website) if user_row.website else "",
                "profile_img": AESService.decrypt(user_row.profile_img) if user_row.profile_img else "",
                "role": AESService.decrypt(user_row.role)
            }

            if address_row:
                profile_data["address"] = {
                    "country": AESService.decrypt(address_row.country),
                    "city": AESService.decrypt(address_row.city),
                    "address_line": AESService.decrypt(address_row.address_line),
                    "postal_code": AESService.decrypt(address_row.postal_code)
                }
            else:
                profile_data["address"] = {
                    "country": "",
                    "city": "",
                    "address_line": "",
                    "postal_code": ""
                }

            return jsonify(profile_data), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
