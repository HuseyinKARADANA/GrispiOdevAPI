# user_controller.py
from flask import Blueprint, request, jsonify
import os, re, pyodbc, bcrypt, jwt, datetime, requests
from service.aes_service import AESService
# user_controller.py (en üst kısım)
from service.mailer import send_welcome_email
user_controller = Blueprint("user_controller", __name__)

# ---- Config ----
GRISPI_TOKEN      = os.getenv("GRISPI_TOKEN")                 # Bearer token
GRISPI_TENANT     = os.getenv("GRISPI_TENANT", "stajer")      # örn: "stajer"
GRISPI_BASE       = "https://api.grispi.com/public/v1"
CONNECTION_STRING = os.getenv("CONNECTION_STRING")
SECRET_KEY        = os.getenv("SECRET_KEY")


# ---------------- Helpers ----------------
def to_e164_tr(raw):
    """TR numarayı E.164 +90... formatına çevir."""
    if not raw: return None
    s = str(raw).strip().replace(" ", "")
    if s.startswith("+90"): return s
    if s.startswith("90"):  return f"+{s}"
    if s.startswith("0"):   return f"+90{s[1:]}"
    if len(s) == 10 and s.isdigit(): return f"+90{s}"
    return s

def sanitize_fullname(name, surname):
    """Grispi fullName kurallarına uygun (harf+boşluk)."""
    full = f"{name} {surname}".strip()
    full = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü\s]", "", full)  # rakam/sembol temizle
    full = re.sub(r"\s+", " ", full).strip()
    return full

def grispi_headers_json():
    return {
        "Authorization": f"Bearer {GRISPI_TOKEN}",
        "tenantId": GRISPI_TENANT,           # Yalnızca harf-rakam-tire; nokta kullanma.
        "Content-Type": "application/json"
    }

def grispi_create_customer(email, phone, full_name, organization=None, tags=None, fields=None):
    """
    POST /customers — requests.Response döner (status_code, text, json()).
    Başarısız olursa (TAKEN vs.), caller gerekirse search ile bulabilir.
    """
    payload = {
        "email": email,
        "phone": to_e164_tr(phone) if phone else None,
        "fullName": full_name
    }
    if organization: payload["organization"] = organization
    if tags:         payload["tags"] = tags
    if fields:       payload["fields"] = fields

    # None/boşları temizle
    payload = {k: v for k, v in payload.items() if v not in (None, "", [])}

    resp = requests.post(f"{GRISPI_BASE}/customers",
                         headers=grispi_headers_json(),
                         json=payload,
                         timeout=20)
    return resp

def grispi_find_customer_by_email(email):
    """GET /customers/search -> ilk kayıt JSON (yoksa None)."""
    try:
        r = requests.get(f"{GRISPI_BASE}/customers/search",
                         headers=grispi_headers_json(),
                         params={"searchTerm": email, "size": 1, "page": 0},
                         timeout=12)
        if r.status_code == 200:
            js = r.json()
            if js.get("content"):
                return js["content"][0]  # { id, email, fullName, ... }
    except Exception as ex:
        print("⚠️ Grispi search hata:", ex)
    return None


# ---------------- REGISTER ----------------
@user_controller.route('/register', methods=['POST'])
def register_user():
    try:
        data = request.get_json()
        print("📥 Gelen JSON:", data)

        required = ['name', 'surname', 'preliminary_phone', 'preliminary_email', 'password', 'role']
        if not all(k in data for k in required):
            return jsonify({"error": "Gerekli alanlar eksik"}), 400

        name              = data['name']
        surname           = data['surname']
        preliminary_phone = data['preliminary_phone']
        preliminary_email = data['preliminary_email']
        password_bytes    = data['password'].encode('utf-8')
        role              = data['role']

        # AES ile şifrele (lokal DB alanları)
        enc_name    = AESService.encrypt(name)
        enc_surname = AESService.encrypt(surname)
        enc_phone   = AESService.encrypt(preliminary_phone)
        enc_email   = AESService.encrypt(preliminary_email)
        enc_role    = AESService.encrypt(role)

        # bcrypt + AES (parola)
        hashed_password = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')
        enc_password    = AESService.encrypt(hashed_password)

        # ----- DB INSERT + yeni kullanıcının id'si -----
        with pyodbc.connect(CONNECTION_STRING) as db:
            cur = db.cursor()

            cur.execute("SELECT COUNT(*) FROM TblUser WHERE preliminary_email = ?", (enc_email,))
            if cur.fetchone()[0] > 0:
                return jsonify({"error": "Bu e-posta zaten kayıtlı!"}), 400

            cur.execute("""
                INSERT INTO TblUser (name, surname, preliminary_phone, preliminary_email, password, role, is_active, created_at)
                OUTPUT INSERTED.id
                VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
            """, (enc_name, enc_surname, enc_phone, enc_email, enc_password, enc_role, 1))
            new_user_id = cur.fetchone()[0]
            db.commit()

        # ----- Grispi müşteri oluştur -----
        full_name    = sanitize_fullname(name, surname)
        organization = data.get("organization") or None  # Grispi'de yoksa gönderme
        tags         = [role, "yeni_kayit"]
        fields       = data.get("fields") if isinstance(data.get("fields"), list) else None

        grispi_response_json = None
        grispi_id_to_store   = None

        if not GRISPI_TOKEN:
            print("⚠️ GRISPI_TOKEN yok; Grispi POST atlanıyor.")
        else:
            try:
                resp = grispi_create_customer(
                    email=preliminary_email,
                    phone=preliminary_phone,
                    full_name=full_name,
                    organization=organization,
                    tags=tags,
                    fields=fields
                )
                print("📡 Grispi status:", resp.status_code)
                print("📡 Grispi body:", resp.text)

                if resp.status_code in (200, 201):
                    grispi_response_json = resp.json()
                    grispi_id_to_store   = grispi_response_json.get("id")
                else:
                    # Örn: phone TAKEN, organization not found vs.
                    found = grispi_find_customer_by_email(preliminary_email)
                    if found:
                        grispi_response_json = found
                        grispi_id_to_store   = found.get("id")

            except Exception as ex:
                print("⚠️ Grispi müşteri oluşturma/arama hatası:", ex)

        # ----- Grispi ID'yi TblUser.grispiId kolonuna yaz -----
        if grispi_id_to_store:
            try:
                with pyodbc.connect(CONNECTION_STRING) as db:
                    cur = db.cursor()
                    cur.execute("UPDATE TblUser SET grispiId = ? WHERE id = ?", (grispi_id_to_store, new_user_id))
                    db.commit()
                print(f"✅ TblUser.grispiId güncellendi: {grispi_id_to_store}")
            except Exception as ex:
                print("⚠️ Grispi ID tabloya yazılırken hata:", ex)

        try:
            if os.getenv("EMAIL_ENABLED", "true").lower() in ("1", "true", "yes"):
                send_welcome_email(preliminary_email, name)
        except Exception as e:
            print(f"📧 Hoş geldin maili gönderilemedi: {e}")


        # ----- Client response: Grispi yanıtı da dahil -----
        return jsonify({
            "message": "Kullanıcı başarıyla eklendi!",
            "user": {
                "id": new_user_id,
                "name": name,
                "surname": surname,
                "email": preliminary_email,
                "phone": preliminary_phone
            },
            "grispi": grispi_response_json  # Grispi’nin döndürdüğü JSON (None olabilir)
        }), 200

    except KeyError as e:
        print(f"KeyError: {e}")
        return jsonify({"error": f"Eksik alan: {str(e)}"}), 400
    except pyodbc.Error as e:
        print(f"Veritabanı Hatası: {e}")
        return jsonify({"error": "Veritabanı hatası oluştu."}), 500
    except Exception as e:
        print(f"Genel Hata: {e}")
        return jsonify({"error": "Sunucu hatası oluştu."}), 500


# ---------------- LOGIN ----------------
@user_controller.route('/login', methods=['POST'])
def login():
    """Mail ve şifre ile giriş yapar ve JWT'ye grispi_id ekler."""
    try:
        data = request.get_json()
        print("📥 Gelen JSON:", data)

        if not all(k in data for k in ('email', 'password')):
            return jsonify({"error": "Gerekli alanlar eksik"}), 400

        email      = data['email']
        password   = data['password'].encode('utf-8')
        rememberMe = data.get('rememberMe', False)

        # AES ile email'i şifrele
        encrypted_email = AESService.encrypt(email)

        with pyodbc.connect(CONNECTION_STRING) as db:
            cursor = db.cursor()
            cursor.execute("""
                SELECT id, name, surname, password, role, grispiId
                FROM TblUser 
                WHERE preliminary_email = ? AND is_active = 1
            """, (encrypted_email,))
            result = cursor.fetchone()

        if not result:
            return jsonify({"error": "Geçersiz e-posta veya şifre"}), 401

        user_id, enc_name, enc_surname, enc_password, enc_role, db_grispi_id = result

        # bcrypt karşılaştır
        decrypted_password = AESService.decrypt(enc_password)
        if not bcrypt.checkpw(password, decrypted_password.encode('utf-8')):
            return jsonify({"error": "Geçersiz e-posta veya şifre"}), 401

        # Kullanıcı bilgilerini çöz
        name    = AESService.decrypt(enc_name)
        surname = AESService.decrypt(enc_surname)
        role    = AESService.decrypt(enc_role)

        # ---- Grispi ID: Önce DB, yoksa email ile bul ve DB'ye yaz ----
        grispi_id = db_grispi_id
        if not grispi_id and GRISPI_TOKEN:
            try:
                found = grispi_find_customer_by_email(email)
                if found:
                    grispi_id = found.get("id")
                    print(f"✅ Grispi ID (fallback) bulundu: {grispi_id}")
                    # DB'ye geri yaz
                    with pyodbc.connect(CONNECTION_STRING) as db:
                        cur = db.cursor()
                        cur.execute("UPDATE TblUser SET grispiId = ? WHERE id = ?", (grispi_id, user_id))
                        db.commit()
                else:
                    print("⚠️ Grispi'de müşteri bulunamadı (email ile).")
            except Exception as ex:
                print("⚠️ Grispi arama hatası:", ex)
        elif not GRISPI_TOKEN:
            print("⚠️ GRISPI_TOKEN yok; Grispi araması atlandı.")

        # JWT üret
        expire_time = datetime.timedelta(days=7) if rememberMe else datetime.timedelta(hours=8)
        exp = datetime.datetime.utcnow() + expire_time

        payload = {
            "id": user_id,
            "name": name,
            "surname": surname,
            "email": email,
            "role": role,
            "grispi_id": grispi_id,  # token'a eklendi
            "exp": int(exp.timestamp())
        }

        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

        # Konsol log
        print("🔐 Login payload:", payload)

        return jsonify({
            "message": "Giriş başarılı!",
            "token": token
        }), 200

    except pyodbc.Error as e:
        print(f"🚨 MSSQL Hatası: {e}")
        return jsonify({"error": "Veritabanı hatası"}), 500
    except Exception as e:
        print(f"🚨 Genel Hata: {e}")
        return jsonify({"error": "Dahili Sunucu Hatası"}), 500
