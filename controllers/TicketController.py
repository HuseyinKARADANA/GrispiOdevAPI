from flask import Blueprint, request, jsonify
from service.auth import token_required
from service.aes_service import AESService
from datetime import datetime
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import uuid
import os, requests, pyodbc, math, datetime
from flask import jsonify, request
# ticket_controller.py (üst kısım)
from service.mailer import send_ticket_opened_email
load_dotenv()

ticket_controller = Blueprint('ticket_controller', __name__)
CONNECTION_STRING = os.getenv("CONNECTION_STRING")

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'docx', 'xlsx'}


GRISPI_TOKEN  = os.getenv("GRISPI_TOKEN")
GRISPI_TENANT = os.getenv("GRISPI_TENANT", "stajer")
GRISPI_BASE   = "https://api.grispi.com/public/v1"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def to_e164_tr(raw):
    if not raw: return None
    s = str(raw).strip().replace(" ", "")
    if s.startswith("+90"): return s
    if s.startswith("90"):  return f"+{s}"
    if s.startswith("0"):   return f"+90{s[1:]}"
    if len(s) == 10 and s.isdigit(): return f"+90{s}"
    return s




def _ms_to_date(ms):
    try:
        return datetime.datetime.utcfromtimestamp(int(ms)/1000.0)
    except Exception:
        return None

def _safe_field(field_map, key, subkey="userFriendlyValue"):
    try:
        fm = field_map.get(key) or {}
        # priority/status gibi alanlarda userFriendlyValue; subject'te hem value hem userFriendlyValue olabilir
        return fm.get(subkey) or fm.get("value") or fm.get("serializedValue")
    except Exception:
        return None

def _get_grispi_user_id_from_token_or_lookup(user_id: int):
    """
    token_required içinde request.grispi_id veya request.jwt_payload['grispi_id'] varsa onu kullan.
    Yoksa DB’den email’i decrypt edip Grispi search ile id bul.
    """
    grispi_id = getattr(request, "grispi_id", None)
    if not grispi_id:
        jwt_payload = getattr(request, "jwt_payload", {}) or {}
        grispi_id = jwt_payload.get("grispi_id")

    if grispi_id:
        return grispi_id

    # Fallback: DB'den email'i çöz, Grispi’de search et
    with pyodbc.connect(CONNECTION_STRING) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT preliminary_email
            FROM TblUser WHERE id = ?
        """, (user_id,))
        row = c.fetchone()
    if not row:
        return None

    enc_email = row[0]
    email = AESService.decrypt(enc_email) if enc_email else None
    if not email:
        return None

    headers = {
        "Authorization": f"Bearer {GRISPI_TOKEN}",
        "tenantId": GRISPI_TENANT,
        "Content-Type": "application/json",
    }
    try:
        r = requests.get(f"{GRISPI_BASE}/customers/search",
                         headers=headers,
                         params={"searchTerm": email, "size": 1, "page": 0},
                         timeout=12)
        if r.status_code == 200 and r.json().get("content"):
            return r.json()["content"][0]["id"]
    except Exception as ex:
        print("⚠️ Grispi search hata:", ex)
    return None
@ticket_controller.route('/create', methods=['POST'])
@token_required
def create_ticket():
    """
    Ticket oluşturur; lokal DB'ye kaydeder, Grispi'ye POST eder.
    Başarılı/başarısız her iki senaryoda da kullanıcıya 'talep alındı' maili atmayı dener.
    """
    try:
        subject = request.form.get('subject')
        category_id = request.form.get('category_id')
        priority = request.form.get('priority')
        description = request.form.get('description')
        files = request.files.getlist('attachments')

        if not subject or not category_id or not priority:
            return jsonify({'error': 'Zorunlu alanlar eksik'}), 400

        created_date = datetime.datetime.now()
        user_id = request.user_id
        assigned_user_id = None
        status = "OPEN"
        update_date = created_date

        # --- Kullanıcı email/telefonu (mail + Grispi creator için) ---
        with pyodbc.connect(CONNECTION_STRING) as conn_lookup:
            c2 = conn_lookup.cursor()
            c2.execute("""
                SELECT preliminary_email, preliminary_phone
                FROM TblUser WHERE id = ?
            """, (user_id,))
            row = c2.fetchone()
        user_email = AESService.decrypt(row[0]) if row and row[0] else None
        user_phone = AESService.decrypt(row[1]) if row and row[1] else None

        # --- Lokal DB kaydı ---
        enc_subject = AESService.encrypt(subject)
        enc_description = AESService.encrypt(description) if description else None
        enc_priority = AESService.encrypt(priority)
        enc_status = AESService.encrypt(status)

        with pyodbc.connect(CONNECTION_STRING) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO TblTicket (
                    user_id, assigned_user_id, subject, category_id, 
                    description, priority, status, update_date, created_date
                )
                OUTPUT INSERTED.TicketId
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, assigned_user_id, enc_subject, category_id,
                enc_description, enc_priority, enc_status, update_date, created_date
            ))
            ticket_id = cursor.fetchone()[0]

            # Dosyaları lokalde sakla
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
                    file.save(filepath)

                    enc_filename = AESService.encrypt(filename)
                    enc_filepath = AESService.encrypt(filepath)
                    cursor.execute("""
                        INSERT INTO TblFolder (ticket_id, file_name, file_path, created_at)
                        VALUES (?, ?, ?, ?)
                    """, (ticket_id, enc_filename, enc_filepath, created_date))

            conn.commit()

        # --- İç helper: mail gönder (best-effort) ---
        def _notify_open(ticket_no: str):
            try:
                if os.getenv("EMAIL_ENABLED", "true").lower() in ("1", "true", "yes") and user_email:
                    sent = send_ticket_opened_email(user_email, ticket_no=ticket_no, title=subject)
                    print(f"📧 ticket_opened mail -> {user_email} | sent={sent} | ticket_no={ticket_no}")
                else:
                    print("📧 mail atlanıyor: EMAIL_ENABLED=false veya user_email boş")
            except Exception as e:
                print(f"📧 Talep açılış maili gönderilemedi: {e}")

        # --- Grispi'de ticket oluştur ---
        grispi_headers = {
            "Authorization": f"Bearer {GRISPI_TOKEN}",
            "tenantId": GRISPI_TENANT,
            "Content-Type": "application/json"
        }
        body_text = description if (description and description.strip()) else subject
        creator = []
        if user_email:
            creator.append({"key": "us.email", "value": user_email})
        if user_phone:
            creator.append({"key": "us.phone", "value": to_e164_tr(user_phone)})

        grispi_payload = {
            "comment": {
                "body": body_text,
                "publicVisible": False,
                "creator": creator
            },
            "fields": [
                {"key": "ts.subject", "value": subject}
            ]
        }

        grispi_ticket_key = None
        try:
            g_resp = requests.post(
                f"{GRISPI_BASE}/tickets",
                headers=grispi_headers,
                json=grispi_payload,
                timeout=20
            )
            print("🎫 Grispi ticket POST status:", g_resp.status_code)
            print("🎫 Grispi ticket response:", g_resp.text)

            if g_resp.status_code in (200, 201):
                gjson = g_resp.json()
                grispi_ticket_key = gjson.get("key") or gjson.get("id")

                # -- Mail: Grispi + lokal başarılı
                _notify_open(str(grispi_ticket_key or ticket_id))

                return jsonify({
                    'message': 'Destek talebi başarıyla oluşturuldu',
                    'ticket_id': ticket_id,
                    'grispi_ticket_key': grispi_ticket_key
                }), 201
            else:
                # -- Mail: Grispi başarısız, ama lokal var
                _notify_open(str(ticket_id))

                return jsonify({
                    'message': 'Destek talebi oluşturuldu (lokal). Grispi oluşturulamadı.',
                    'ticket_id': ticket_id,
                    'grispi_error': g_resp.text
                }), 201

        except Exception as ex:
            print("⚠️ Grispi ticket create isteği başarısız:", ex)

            # -- Mail: Ağ/servis hatası; lokal var
            _notify_open(str(ticket_id))

            return jsonify({
                'message': 'Destek talebi oluşturuldu (lokal). Grispi bağlantısı başarısız.',
                'ticket_id': ticket_id
            }), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ticket_controller.route('/my-requests', methods=['GET'])
@token_required
def get_tickets_by_user():
    try:
        # Auth'lu kullanıcı (sen zaten token_required ile set ediyorsun)
        grispi_user_id  = request.grispi_id
        print(grispi_user_id)
        # İstemci sayfalaması
        page = max(int(request.args.get('page', 1)), 1)
        per_page = max(int(request.args.get('per_page', 10)), 1)
        start = (page - 1) * per_page
        end   = start + per_page


        # 2) Grispi’den talepleri çek
        headers = {
            "Authorization": f"Bearer {GRISPI_TOKEN}",
            "tenantId": GRISPI_TENANT,
            "Content-Type": "application/json"
        }
        resp = requests.get(
            f"{GRISPI_BASE}/users/{grispi_user_id}/tickets",
            headers=headers,
            timeout=20
        )

        # --- DEBUG LOG ---
        print("🔹 Grispi status code:", resp.status_code)
        try:
            print("🔹 Grispi response JSON:", resp.json())
        except Exception:
            print("🔹 Grispi raw text:", resp.text)
        # -----------------

        if resp.status_code != 200:
            return jsonify({
                "error": "Grispi isteği başarısız",
                "details": resp.text
            }), 502

        if resp.status_code != 200:
            return jsonify({
                "error": "Grispi isteği başarısız",
                "details": resp.text
            }), 502

        tickets = resp.json() if isinstance(resp.json(), list) else resp.json().get("content", [])
        # Not: Swagger “en fazla 100 açık talep” diyor; kapalıları dönmüyorsa bu beklenen davranış.

        # 3) Dönüşleri bizim şemaya map et
        mapped = []
        for t in tickets:
            # Bazı alanlar response kökünde, bazıları fieldMap içinde
            key = t.get("key")  # örn: TICKET-1
            createdAt = _ms_to_date(t.get("createdAt"))
            updatedAt = _ms_to_date(t.get("updatedAt"))

            field_map = t.get("fieldMap") or {}

            subject  = _safe_field(field_map, "ts.subject") or t.get("subject")
            status   = _safe_field(field_map, "ts.status") or ""
            priority = _safe_field(field_map, "ts.priority") or ""

            mapped.append({
                "ticket_id": key or "",  # senin eski UI’da #123 gibi gösteriyordun, burada key daha anlamlı
                "subject": subject or "",
                "priority": str(priority).upper() if priority else "",
                "status": str(status).upper() if status else "",
                "category": None,  # Grispi tarafında kategori alanı ayrıysa buraya map edebilirsin
                "update_date": updatedAt.strftime('%d.%m.%Y') if updatedAt else None,
                "created_date": createdAt.strftime('%d.%m.%Y') if createdAt else None
            })

        total_count = len(mapped)
        paged = mapped[start:end]
        total_pages = math.ceil(total_count / per_page) if per_page else 1

        return jsonify({
            "data": paged,
            "pagination": {
                "total_items": total_count,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500



@ticket_controller.route('/<int:ticket_id>/detail', methods=['GET'])
@token_required
def ticket_detail(ticket_id):
    def dec(v):
        try:
            return AESService.decrypt(v) if v else None
        except Exception:
            # yanlış/çift şifreleme vs. durumlarında endpoint çökmesin
            return v

    try:
        with pyodbc.connect(CONNECTION_STRING) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT t.TicketId, t.user_id, t.assigned_user_id,
                       t.subject, t.category_id, t.description,
                       t.priority, t.status, t.update_date, t.created_date,
                       ru.name AS requester_name, ru.surname AS requester_surname,
                       au.name AS assignee_name, au.surname AS assignee_surname,
                       c.category_name
                FROM TblTicket t
                LEFT JOIN TblUser ru ON ru.id = t.user_id
                LEFT JOIN TblUser au ON au.id = t.assigned_user_id
                LEFT JOIN TblCategory c ON c.id = t.category_id
                WHERE t.TicketId = ?
            """, (ticket_id,))
            t = cur.fetchone()
            if not t:
                return jsonify({'error': 'Ticket bulunamadı'}), 404

            pr = dec(t.priority)
            st = dec(t.status)

            ticket = {
                'ticket_id': t.TicketId,
                'requester': {
                    'id': t.user_id,
                    'name': dec(t.requester_name),
                    'surname': dec(t.requester_surname)
                },
                'assignee': (
                    {
                        'id': t.assigned_user_id,
                        'name': dec(t.assignee_name),
                        'surname': dec(t.assignee_surname)
                    } if t.assigned_user_id else None
                ),
                'subject': dec(t.subject),
                'category_id': t.category_id,
                'category_name': dec(t.category_name),
                'description': dec(t.description),
                'priority': pr.upper() if pr else None,
                'status': st.upper() if st else None,
                'update_date': t.update_date,
                'created_date': t.created_date
            }

            # CC listesi (isimler deşifre)
            cur.execute("""
                SELECT cc.user_id, u.name, u.surname
                FROM TblTicketCC cc
                LEFT JOIN TblUser u ON u.id = cc.user_id
                WHERE cc.ticket_id = ?
            """, (ticket_id,))
            ccs = [{'user_id': r.user_id, 'name': dec(r.name), 'surname': dec(r.surname)}
                   for r in cur.fetchall()]

            # Followers (isimler deşifre)
            cur.execute("""
                SELECT f.user_id, u.name, u.surname
                FROM TblTicketFollower f
                LEFT JOIN TblUser u ON u.id = f.user_id
                WHERE f.ticket_id = ?
            """, (ticket_id,))
            followers = [{'user_id': r.user_id, 'name': dec(r.name), 'surname': dec(r.surname)}
                         for r in cur.fetchall()]

            # Mesajlar + ekler (zaten şifre çözüyordun; helper’a da aldım)
            cur.execute("""
                SELECT m.id, m.sender_user_id, m.message_text, m.created_at, m.is_internal
                FROM TblTicketMessage m
                WHERE m.ticket_id = ?
                ORDER BY m.created_at ASC
            """, (ticket_id,))
            messages = []
            for mr in cur.fetchall():
                msg = {
                    'id': mr.id,
                    'sender_user_id': mr.sender_user_id,
                    'message_text': dec(mr.message_text),
                    'created_at': mr.created_at,
                    'is_internal': mr.is_internal
                }
                cur2 = conn.cursor()
                cur2.execute("""
                    SELECT id, file_name, file_path, uploaded_at
                    FROM TblTicketMessageAttachment
                    WHERE message_id = ?
                """, (mr.id,))
                msg['attachments'] = [{
                    'id': a.id,
                    'file_name': dec(a.file_name),
                    'file_path': dec(a.file_path),
                    'uploaded_at': a.uploaded_at
                } for a in cur2.fetchall()]
                messages.append(msg)

            return jsonify({'ticket': ticket, 'ccs': ccs, 'followers': followers, 'messages': messages}), 200

    except Exception as e:
        print('ticket_detail err:', e)
        return jsonify({'error': 'Sunucu hatası'}), 500


@ticket_controller.route('/<int:ticket_id>/messages', methods=['POST'])
@token_required
def add_ticket_message(ticket_id):
    try:
        data = request.get_json()
        message_text = (data.get('message_text') or '').strip()
        is_internal = int(data.get('is_internal', 0))
        if not message_text:
            return jsonify({'error': 'Mesaj boş olamaz'}), 400

        with pyodbc.connect(CONNECTION_STRING) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO TblTicketMessage (ticket_id, sender_user_id, message_text, created_at, is_internal)
                OUTPUT INSERTED.id
                VALUES (?, ?, ?, GETDATE(), ?)
            """, (ticket_id, request.user_id, AESService.encrypt(message_text), is_internal))
            mid = cur.fetchone()[0]
            cur.execute("UPDATE TblTicket SET update_date = GETDATE() WHERE TicketId = ?", (ticket_id,))
            conn.commit()
        return jsonify({'message_id': mid}), 201
    except Exception as e:
        print('add_message err:', e)
        return jsonify({'error': 'Sunucu hatası'}), 500



@ticket_controller.route('/<int:ticket_id>', methods=['PATCH'])
@token_required
def update_ticket(ticket_id):
    try:
        data = request.get_json()
        sets, params = [], []
        if 'status' in data:
            sets.append("status=?"); params.append(AESService.encrypt(str(data['status'])))
        if 'priority' in data:
            sets.append("priority=?"); params.append(AESService.encrypt(str(data['priority'])))
        if 'assigned_user_id' in data:
            sets.append("assigned_user_id=?"); params.append(int(data['assigned_user_id']))
        if not sets:
            return jsonify({'error': 'Güncellenecek alan yok'}), 400

        with pyodbc.connect(CONNECTION_STRING) as conn:
            cur = conn.cursor()
            sql = f"UPDATE TblTicket SET {', '.join(sets)}, update_date=GETDATE() WHERE TicketId=?"
            params.append(ticket_id)
            cur.execute(sql, tuple(params))
            conn.commit()
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print('update_ticket err:', e)
        return jsonify({'error': 'Sunucu hatası'}), 500


@ticket_controller.route('/<int:ticket_id>/cc', methods=['POST'])
@token_required
def add_cc(ticket_id):
    try:
        uid = int(request.json.get('user_id'))
        with pyodbc.connect(CONNECTION_STRING) as conn:
            cur = conn.cursor()
            cur.execute("""
                MERGE TblTicketCC AS t
                USING (SELECT ? AS ticket_id, ? AS user_id) AS s
                  ON t.ticket_id=s.ticket_id AND t.user_id=s.user_id
                WHEN NOT MATCHED THEN
                  INSERT (ticket_id, user_id, created_at) VALUES (s.ticket_id, s.user_id, GETDATE());
            """, (ticket_id, uid))
            conn.commit()
        return jsonify({'status': 'ok'}), 201
    except Exception as e:
        print('add_cc err:', e); return jsonify({'error': 'Sunucu hatası'}), 500

@ticket_controller.route('/<int:ticket_id>/cc/<int:user_id>', methods=['DELETE'])
@token_required
def remove_cc(ticket_id, user_id):
    try:
        with pyodbc.connect(CONNECTION_STRING) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM TblTicketCC WHERE ticket_id=? AND user_id=?", (ticket_id, user_id))
            conn.commit()
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print('del_cc err:', e); return jsonify({'error': 'Sunucu hatası'}), 500

@ticket_controller.route('/<int:ticket_id>/followers', methods=['POST'])
@token_required
def add_follower(ticket_id):
    try:
        uid = int(request.json.get('user_id'))
        with pyodbc.connect(CONNECTION_STRING) as conn:
            cur = conn.cursor()
            cur.execute("""
                MERGE TblTicketFollower AS t
                USING (SELECT ? AS ticket_id, ? AS user_id) AS s
                  ON t.ticket_id=s.ticket_id AND t.user_id=s.user_id
                WHEN NOT MATCHED THEN
                  INSERT (ticket_id, user_id, created_at) VALUES (s.ticket_id, s.user_id, GETDATE());
            """, (ticket_id, uid))
            conn.commit()
        return jsonify({'status': 'ok'}), 201
    except Exception as e:
        print('add_follower err:', e); return jsonify({'error': 'Sunucu hatası'}), 500

@ticket_controller.route('/<int:ticket_id>/followers/<int:user_id>', methods=['DELETE'])
@token_required
def remove_follower(ticket_id, user_id):
    try:
        with pyodbc.connect(CONNECTION_STRING) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM TblTicketFollower WHERE ticket_id=? AND user_id=?", (ticket_id, user_id))
            conn.commit()
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print('del_follower err:', e); return jsonify({'error': 'Sunucu hatası'}), 500




@ticket_controller.route('/messages/<int:message_id>/attachments', methods=['POST'])
@token_required
def upload_message_attachment(message_id):
    try:
        file = request.files.get('file')
        if not file or not allowed_file(file.filename):
            return jsonify({'error':'Geçersiz dosya'}), 400
        filename = secure_filename(file.filename)
        unique = f"{uuid.uuid4().hex}_{filename}"
        path = os.path.join(UPLOAD_FOLDER, unique)
        file.save(path)

        with pyodbc.connect(CONNECTION_STRING) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO TblTicketMessageAttachment (message_id, file_name, file_path, uploaded_at)
                VALUES (?, ?, ?, GETDATE())
            """, (message_id, AESService.encrypt(filename), AESService.encrypt(path)))
            conn.commit()
        return jsonify({'status':'ok'}), 201
    except Exception as e:
        print('upload_att err:', e)
        return jsonify({'error':'Sunucu hatası'}), 500


@ticket_controller.route('/all-open', methods=['GET'])
@token_required
def list_all_open_or_unassigned():
    """
    Şifreli status ile SQL tarafında filtre:
      - t.status = <cipher>  (örn: OPEN'in şifreli hali)
      - VEYA assigned_user_id IS NULL (teknisyen atanmamış)
    ?page, ?per_page, ?status_cipher opsiyonel (default: "YdPyZm12BB5UEIiNRTrTcA==")
    """
    try:
        page = max(int(request.args.get('page', 1)), 1)
        per_page = max(int(request.args.get('per_page', 10)), 1)
        offset = (page - 1) * per_page

        # default cipher
        status_cipher = AESService.encrypt("OPEN")

        with pyodbc.connect(CONNECTION_STRING) as conn:
            cur = conn.cursor()

            # toplam adet
            cur.execute("""
                SELECT COUNT(*) 
                FROM TblTicket
                WHERE (status = ? OR assigned_user_id IS NULL)
            """, (status_cipher,))
            total_items = cur.fetchone()[0]

            # sayfalı kayıtlar
            cur.execute("""
                SELECT 
                    t.TicketId, t.user_id, t.assigned_user_id,
                    t.subject, t.category_id, t.priority, t.status,
                    t.update_date, t.created_date,
                    ru.name AS requester_name, ru.surname AS requester_surname,
                    au.name AS assignee_name, au.surname AS assignee_surname,
                    c.category_name
                FROM TblTicket t
                LEFT JOIN TblUser ru ON ru.id = t.user_id
                LEFT JOIN TblUser au ON au.id = t.assigned_user_id
                LEFT JOIN TblCategory c ON c.id = t.category_id
                WHERE (t.status = ? OR t.assigned_user_id IS NULL)
                ORDER BY t.created_date DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, (status_cipher, offset, per_page))
            rows = cur.fetchall()

        data = []
        for r in rows:
            # şifreli alanları çöz
            dec_subject  = AESService.decrypt(r.subject)  if r.subject  else None
            dec_priority = AESService.decrypt(r.priority) if r.priority else None
            dec_status   = AESService.decrypt(r.status)   if r.status   else None

            item = {
                'ticket_id': r.TicketId,
                'subject': dec_subject,
                'category_id': r.category_id,
                'category_name': r.category_name,
                'priority': dec_priority.upper() if dec_priority else None,
                'status': dec_status.upper() if dec_status else None,
                'requester': {
                    'id': r.user_id,
                    'name': AESService.decrypt(r.requester_name),
                    'surname': AESService.decrypt(r.requester_surname)
                },
                'assignee': None if r.assigned_user_id is None else {
                    'id': r.assigned_user_id,
                    'name': AESService.decrypt(r.assignee_name),
                    'surname': AESService.decrypt(r.assignee_surname)
                },
                'update_date': r.update_date,
                'created_date': r.created_date
            }
            data.append(item)

        return jsonify({
            'data': data,
            'pagination': {
                'total_items': total_items,
                'page': page,
                'per_page': per_page,
                'total_pages': (total_items + per_page - 1) // per_page
            }
        }), 200

    except Exception as e:
        print("all-open err:", e)
        return jsonify({'error': 'Sunucu hatası'}), 500


@ticket_controller.route('/<int:ticket_id>/assign', methods=['POST'])
@token_required
def assign_ticket(ticket_id):
    """
    Ticket'a teknisyen (assigned_user_id) atar.
    Body: { "assigned_user_id": 5 }
    """
    try:

        assigned_user_id = request.user_id

        if assigned_user_id is None:
            return jsonify({"error": "assigned_user_id zorunludur"}), 400

        with pyodbc.connect(CONNECTION_STRING) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE TblTicket
                SET assigned_user_id = ?, update_date = GETDATE()
                WHERE TicketId = ?
            """, (assigned_user_id, ticket_id))
            conn.commit()

        return jsonify({
            "message": "Ticket başarıyla atandı",
            "ticket_id": ticket_id,
            "assigned_user_id": assigned_user_id
        }), 200

    except Exception as e:
        print("assign_ticket err:", e)
        return jsonify({"error": "Sunucu hatası"}), 500
