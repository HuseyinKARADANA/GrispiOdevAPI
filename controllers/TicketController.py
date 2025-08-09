from flask import Blueprint, request, jsonify
from service.auth import token_required
from service.aes_service import AESService
import pyodbc
import os
from datetime import datetime
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import uuid

load_dotenv()

ticket_controller = Blueprint('ticket_controller', __name__)
CONNECTION_STRING = os.getenv("CONNECTION_STRING")

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'docx', 'xlsx'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@ticket_controller.route('/create', methods=['POST'])
@token_required
def create_ticket():
    try:
        subject = request.form.get('subject')
        category_id = request.form.get('category_id')
        priority = request.form.get('priority')
        description = request.form.get('description')
        files = request.files.getlist('attachments')

        if not subject or not category_id or not priority:
            return jsonify({'error': 'Zorunlu alanlar eksik'}), 400

        created_date = datetime.now()
        user_id = request.user_id
        assigned_user_id = None
        status = "OPEN"
        update_date = created_date

        # AES ile şifreleme
        enc_subject = AESService.encrypt(subject)
        enc_description = AESService.encrypt(description) if description else None
        enc_priority = AESService.encrypt(priority)
        enc_status = AESService.encrypt(status)

        with pyodbc.connect(CONNECTION_STRING) as conn:
            cursor = conn.cursor()

            # Ticket oluştur
            cursor.execute("""
                INSERT INTO TblTicket (
                    user_id, assigned_user_id, subject, category_id, 
                    description, priority, status, update_date, created_date
                )
                OUTPUT INSERTED.TicketId
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                assigned_user_id,
                enc_subject,
                category_id,
                enc_description,
                enc_priority,
                enc_status,
                update_date,
                created_date
            ))

            ticket_id = cursor.fetchone()[0]

            # Dosyaları işle
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

        return jsonify({'message': 'Destek talebi başarıyla oluşturuldu', 'ticket_id': ticket_id}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@ticket_controller.route('/my-requests', methods=['GET'])
@token_required
def get_tickets_by_user():
    try:
        user_id = request.user_id

        # Sayfa ve limit parametreleri
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        offset = (page - 1) * per_page

        with pyodbc.connect(CONNECTION_STRING) as conn:
            cursor = conn.cursor()

            # Toplam kayıt sayısı
            cursor.execute("""
                SELECT COUNT(*)
                FROM TblTicket
                WHERE user_id = ?
            """, (user_id,))
            total_count = cursor.fetchone()[0]

            # Sayfalı veri çekimi
            cursor.execute("""
                SELECT TicketId, subject, category_id, priority, status, update_date, created_date
                FROM TblTicket
                WHERE user_id = ?
                ORDER BY created_date DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """, (user_id, offset, per_page))

            rows = cursor.fetchall()
            result = []

            for row in rows:
                result.append({
                    'ticket_id': f"#{row.TicketId}",
                    'subject': AESService.decrypt(row.subject),
                    'priority': AESService.decrypt(row.priority).upper(),
                    'status': AESService.decrypt(row.status).upper(),
                    'category': f"category{row.category_id}",
                    'update_date': row.update_date.strftime('%d.%m.%Y') if row.update_date else None,
                    'created_date': row.created_date.strftime('%d.%m.%Y') if row.created_date else None
                })

        response = {
            'data': result,
            'pagination': {
                'total_items': total_count,
                'page': page,
                'per_page': per_page,
                'total_pages': (total_count + per_page - 1) // per_page
            }
        }

        return jsonify(response), 200

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
