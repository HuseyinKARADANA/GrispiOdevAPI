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
                WHERE email = ? AND is_active = 1
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
                    "user": {
                        "id": user_id,
                        "name": name,
                        "surname": surname,
                        "email": email,
                        "role": role
                    },
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


@user_controller.route('/create_new_password', methods=['POST'])
@token_required
def create_new_password():
    try:
        data = request.get_json()
        print("Gelen JSON:", data)

        if not all(k in data for k in ('email', 'password', 'newpassword')):
            return jsonify({"error": "Gerekli alanlar eksik"}), 400

        email = data['email']
        current_password = data['password']
        new_password = data['newpassword']

        encrypted_email = AESService.encrypt(email)

        with pyodbc.connect(CONNECTION_STRING) as db:
            cursor = db.cursor()
            cursor.execute("SELECT password FROM TblUser WHERE email = ?", (encrypted_email,))
            result = cursor.fetchone()

        if result:
            encrypted_password_from_db = result[0]

            # Veritabanındaki şifreyi önce AES ile çöz
            decrypted_password = AESService.decrypt(encrypted_password_from_db)

            # Şifre eşleşiyor mu?
            if bcrypt.checkpw(current_password.encode('utf-8'), decrypted_password.encode('utf-8')):

                # Yeni şifreyi bcrypt ile hashle ve sonra AES ile şifrele
                new_hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                encrypted_new_password = AESService.encrypt(new_hashed)

                with pyodbc.connect(CONNECTION_STRING) as db:
                    cursor = db.cursor()
                    cursor.execute("UPDATE TblUser SET password = ? WHERE email = ?",
                                   (encrypted_new_password, encrypted_email))
                    db.commit()

                return jsonify({"message": "Şifre başarıyla güncellendi!"}), 200
            else:
                return jsonify({"error": "Geçerli şifre hatalı."}), 401
        else:
            return jsonify({"error": "Bu e-posta adresi kayıtlı değil."}), 404

    except pyodbc.Error as e:
        print(f"MSSQL Hatası: {e}")
        return jsonify({"error": "Veritabanı hatası"}), 500
    except Exception as e:
        print(f"Genel Hata: {e}")
        return jsonify({"error": "Dahili sunucu hatası"}), 500


@user_controller.route('/update_user', methods=['POST'])
@token_required
def update_user(current_user):
    try:
        data = request.get_json()
        print("📥 Gelen JSON:", data)

        if 'preliminary_email' not in data:
            return jsonify({"error": "Güncellenecek kullanıcı e-postası zorunludur."}), 400

        encrypted_email = AESService.encrypt(data['preliminary_email'])

        # Güncellenebilir alanlar
        updatable_fields = {
            'name': 'name',
            'surname': 'surname',
            'preliminary_phone': 'preliminary_phone',
            'new_email': 'preliminary_email',  # özel
            'role': 'role',
            'profile_img': 'profile_img',
            'website': 'website'
        }

        update_data = {}

        for field, column in updatable_fields.items():
            if field in data:
                update_data[column] = AESService.encrypt(data[field])

        if 'password' in data:
            hashed_pw = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            update_data['password'] = AESService.encrypt(hashed_pw)

        if not update_data:
            return jsonify({"error": "Güncellenecek herhangi bir veri bulunamadı."}), 400

        set_clause = ", ".join([f"{col} = ?" for col in update_data.keys()])
        values = list(update_data.values())
        values.append(encrypted_email)  # WHERE koşulu

        query = f"UPDATE TblUser SET {set_clause} WHERE preliminary_email = ?"

        with pyodbc.connect(CONNECTION_STRING) as db:
            cursor = db.cursor()
            cursor.execute(query, values)
            db.commit()

        return jsonify({"message": "Kullanıcı bilgileri başarıyla güncellendi."}), 200

    except pyodbc.Error as e:
        print(f"🚨 MSSQL Hatası: {e}")
        return jsonify({"error": "Veritabanı hatası"}), 500
    except Exception as e:
        print(f"🚨 Genel Hata: {e}")
        return jsonify({"error": str(e)}), 500



@user_controller.route('/list_users', methods=['GET'])
def list_users():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit

        with pyodbc.connect(CONNECTION_STRING) as db:
            cursor = db.cursor()

            # Toplam kullanıcı sayısı
            cursor.execute("SELECT COUNT(*) FROM TblUser ")
            total_users = cursor.fetchone()[0]

            # Sayfalı kullanıcı verisi
            cursor.execute("""
                SELECT id, name, surname, preliminary_phone, preliminary_email, role, profile_img, website, is_active, created_at
                FROM TblUser
                
                ORDER BY created_at DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, (offset, limit))
            users = cursor.fetchall()

        user_list = []
        for user in users:
            try:
                user_dict = {
                    "id": user.id,
                    "name": AESService.decrypt(user.name),
                    "surname": AESService.decrypt(user.surname),
                    "phone": AESService.decrypt(user.preliminary_phone),
                    "email": AESService.decrypt(user.preliminary_email),
                    "role": AESService.decrypt(user.role),
                    "profile_img": AESService.decrypt(user.profile_img) if user.profile_img else None,
                    "website": AESService.decrypt(user.website) if user.website else None,
                    "is_active": user.is_active,
                    "created_at": user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None
                }
                user_list.append(user_dict)
            except Exception as e:
                print(f"❗ Kullanıcı verisi çözümlenemedi: {e}")
                continue

        return jsonify({
            "users": user_list,
            "page": page,
            "limit": limit,
            "total_users": total_users,
            "total_pages": (total_users + limit - 1) // limit
        }), 200

    except pyodbc.Error as e:
        print(f"🚨 MSSQL Hatası: {e}")
        return jsonify({"error": "Veritabanı hatası"}), 500
    except Exception as e:
        print(f"🚨 Genel Hata: {e}")
        return jsonify({"error": "Dahili Sunucu Hatası"}), 500



@user_controller.route('/get_user/<int:user_id>', methods=['GET'])
@token_required
def get_user_by_id(user_id):
    try:
        with pyodbc.connect(CONNECTION_STRING) as db:
            cursor = db.cursor()
            cursor.execute("""
                SELECT id, name, surname, email, phone, role, is_active, created_at
                FROM TblUser
                WHERE id = ?
            """, (user_id,))
            user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Kullanıcı bulunamadı."}), 404

        # AES ile çöz
        user_data = {
            "id": user.id,
            "name": AESService.decrypt(user.name),
            "surname": AESService.decrypt(user.surname),
            "email": AESService.decrypt(user.email),
            "phone": AESService.decrypt(user.phone),
            "role": AESService.decrypt(user.role),
            "is_active": user.is_active,
            "created_at": user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else None
        }

        return jsonify({"user": user_data}), 200

    except pyodbc.Error as e:
        print(f"🚨 MSSQL Hatası: {e}")
        return jsonify({"error": "Veritabanı hatası"}), 500
    except Exception as e:
        print(f"🚨 Genel Hata: {e}")
        return jsonify({"error": "Dahili Sunucu Hatası"}), 500


@user_controller.route('/delete_user/<int:user_id>', methods=['DELETE'])
@token_required
def delete_user(user_id):
    try:
        with pyodbc.connect(CONNECTION_STRING) as db:
            cursor = db.cursor()

            # Kullanıcı var mı kontrolü
            cursor.execute("SELECT COUNT(*) FROM TblUser WHERE id = ?", (user_id,))
            if cursor.fetchone()[0] == 0:
                return jsonify({"error": "Kullanıcı bulunamadı."}), 404

            # Kullanıcıyı sil
            cursor.execute("DELETE FROM TblUser WHERE id = ?", (user_id,))
            db.commit()

        return jsonify({"message": "Kullanıcı başarıyla silindi."}), 200

    except pyodbc.Error as e:
        print(f"🚨 MSSQL Hatası: {e}")
        return jsonify({"error": "Veritabanı hatası"}), 500
    except Exception as e:
        print(f"🚨 Genel Hata: {e}")
        return jsonify({"error": "Dahili Sunucu Hatası"}), 500
