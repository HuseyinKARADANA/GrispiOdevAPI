# Destek/Ticket API — REST Dokümantasyonu

Flask + MSSQL tabanlı **Ticket/Destek Yönetimi** API'sinin uç noktaları ve kullanım kılavuzu.  
Uygulama; JWT ile **Bearer** kimlik doğrulama, **AES** alan şifreleme, pyodbc ile MSSQL erişimi ve
sayfalama/ek dosya yükleme gibi yetenekler içerir.

> Repo koduna göre base path'ler:  
> - `/User` → Kullanıcı işlemleri  
> - `/Category` → Kategori işlemleri  
> - `/Ticket` → Ticket işlemleri  
> Sunucu varsayılan olarak `http://0.0.0.0:8006` üzerinde koşar. Kullanım rahatlığı için canlıya alınmıştır. http://104.247.173.83:8006 bu url ile uygulamada çalışmaktadır. (bkz. `app.py`).

---

## İçindekiler
- [Kimlik Doğrulama (JWT)](#kimlik-doğrulama-jwt)
- [Hata Modeli](#hata-modeli)
- [Sayfalama](#sayfalama)
- [Yükleme (Dosya/Multipart)](#yükleme-dosyamutlipart)
- [Şifreleme Notları (AES)](#şifreleme-notları-aes)
- [Endpointler](#endpointler)
  - [/ (root)](#-root)
  - [/User](#user)
  - [/Category](#category)
  - [/Ticket](#ticket)
- [Tablo/Model Referansları](#tablomodel-referansları)
- [Güncelleme Notları](#güncelleme-notları)
- [Lisans](#lisans)

---



`.env` örneği:

```env
# Flask
FLASK_ENV=development
SECRET_KEY=jwt-icin-gizli-anahtar

# MSSQL (pyodbc)
CONNECTION_STRING=Driver={ODBC Driver 17 for SQL Server};Server=SERVER;Database=DB;UID=USER;PWD=PASS;Encrypt=yes;TrustServerCertificate=yes;

# SQLAlchemy (config.py içinde DATABASE_URI kullanılıyor)
DATABASE_URI=mssql+pyodbc://USER:PASS@SERVER/DB?driver=ODBC+Driver+17+for+SQL+Server

# AES servisinizin ihtiyaç duyduğu anahtar(lar)
AES_KEY=32-byte-base64-key
```

> Uygulama hem **SQLAlchemy (DATABASE_URI)** hem de **pyodbc (CONNECTION_STRING)** kullanıyor. Her ikisini de tanımlayın.

---

## Kimlik Doğrulama (JWT)

- `POST /User/login` çağrısı ile token alınır.
- Korumalı uçlara `Authorization: Bearer <token>` header’ı ile erişilir.
- `rememberMe` alanı true ise token ~7 gün, değilse ~8 saat geçerli olacak şekilde üretilir.

Örnek:

```http
GET /Ticket/my-requests?page=1&per_page=10 HTTP/1.1
Host: 127.0.0.1:8006
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## Hata Modeli

Sunucu hataları ve doğrulama hataları JSON döner:

```json
{ "error": "Açıklama" }
```

Başlıca HTTP kodları:
- `200 OK`, `201 Created`, `400 Bad Request`, `401 Unauthorized`, `404 Not Found`, `500 Internal Server Error`

---

## Sayfalama

Kullanılan ortak query parametreleri:
- `page` (default: 1)
- `per_page` veya `limit` (endpoint’e göre; default 10/20)

Yanıt örneği:

```json
{
  "data": [ ... ],
  "pagination": {
    "total_items": 125,
    "page": 1,
    "per_page": 10,
    "total_pages": 13
  }
}
```

---

## Yükleme (Dosya/MutliPart)

- Ticket oluştururken (`POST /Ticket/create`) ve mesaj eklerine dosya yüklerken (`POST /Ticket/messages/{message_id}/attachments`) **multipart/form-data** kullanılır.
- İzin verilen uzantılar: `png, jpg, jpeg, pdf, docx, xlsx`
- Dosyalar `uploads/` klasörüne benzersiz isimlerle kaydedilir.

---

## Şifreleme Notları (AES)

- Kullanıcı adı/soyadı/e-posta/telefon, ticket `subject/description/priority/status`, mesaj içerikleri ve dosya meta alanları **AES ile şifrelenir**.
- Listeleme/detay uçlarında gerekli alanlar **decrypted** edilir.
- SQL filtrelemelerinde şifreli alanlar birebir karşılaştırma ister: ör. `status = AES("OPEN")` gibi.

---

## Endpointler

### `/` (root)

#### GET `/`
- **Auth:** Gerekmez
- **Açıklama:** Sağlık kontrolü.
- **Örnek Yanıt:** `"Flask API Çalışıyor!"`

---

### `/User`

#### POST `/User/register`
- **Auth:** Gerekmez
- **Açıklama:** Yeni kullanıcı kaydı oluşturur. Parola **bcrypt** ile hashlenir, hash de **AES** ile saklanır.
- **Body (JSON):**
```json
{
  "name": "Ömer",
  "surname": "Uyanık",
  "preliminary_phone": "+90 5xx xxx xx xx",
  "preliminary_email": "omer@example.com",
  "password": "S3cr3t!",
  "role": "admin"
}
```
- **201/200 Yanıt:**
```json
{ "message": "Kullanıcı başarıyla eklendi!" }
```
- **400 Hata:** Aynı e-posta zaten varsa veya alanlar eksikse.

#### POST `/User/login`
- **Auth:** Gerekmez
- **Açıklama:** E-posta + parola ile oturum açar, JWT döner.
- **Body (JSON):**
```json
{ "email": "omer@example.com", "password": "S3cr3t!", "rememberMe": true }
```
- **200 Yanıt:**
```json
{ "message": "Giriş başarılı!", "token": "..." }
```
- **401/500:** Geçersiz kimlik bilgisi veya sunucu hatası.

#### GET `/User/profile`
- **Auth:** **Gerekir** (Bearer)
- **Açıklama:** Aktif kullanıcının profil ve adres bilgilerini döner (AES çözülmüş).
- **200 Yanıt (örnek):**
```json
{
  "name": "Ömer",
  "surname": "Uyanık",
  "preliminary_phone": "+90 5xx xxx xx xx",
  "preliminary_email": "omer@example.com",
  "website": "",
  "profile_img": "",
  "role": "admin",
  "address": {
    "country": "Türkiye",
    "city": "İstanbul",
    "address_line": "Adres satırı",
    "postal_code": "34000"
  }
}
```

---

### `/Category`

#### POST `/Category/add`
- **Auth:** **Gerekir**
- **Açıklama:** Yeni kategori ekler.
- **Body (JSON):**
```json
{ "category_name": "Donanım" }
```
- **201 Yanıt:**
```json
{ "message": "Kategori başarıyla eklendi" }
```

#### GET `/Category/list`
- **Auth:** **Gerekir**
- **Açıklama:** Tüm kategorileri (en yeni üstte) listeler.
- **200 Yanıt:**
```json
[
  { "id": 1, "category_name": "Donanım", "is_active": true, "created_at": "2025-08-11 10:12:00" }
]
```

#### GET `/Category/active_list`
- **Auth:** **Gerekir**
- **Açıklama:** Sadece aktif kategorileri alfabetik döner.

#### PUT `/Category/update/{category_id}`
- **Auth:** **Gerekir**
- **Açıklama:** Kategori adını ve `is_active` alanını günceller.
- **Body (JSON):**
```json
{ "category_name": "Donanım & Aksesuar", "is_active": 1 }
```
- **200 Yanıt:** `{ "message": "Kategori güncellendi" }`

#### DELETE `/Category/delete/{category_id}`
- **Auth:** **Gerekir**
- **Açıklama:** Kategoriyi siler.
- **200 Yanıt:** `{ "message": "Kategori silindi" }`

---

### `/Ticket`

#### POST `/Ticket/create`
- **Auth:** **Gerekir**
- **Açıklama:** Ticket oluşturur. Multipart form-data beklenir. Ekler (`attachments`) isteğe bağlıdır.
- **Form-Data Alanları:**
  - `subject` (zorunlu, AES)
  - `category_id` (zorunlu)
  - `priority` (zorunlu, AES) — ör. `LOW|MEDIUM|HIGH`
  - `description` (opsiyonel, AES)
  - `attachments` (opsiyonel, çoklu dosya)
- **201 Yanıt:**
```json
{ "message": "Destek talebi başarıyla oluşturuldu", "ticket_id": 42 }
```

`curl` örneği:
```bash
curl -X POST http://127.0.0.1:8006/Ticket/create \
  -H "Authorization: Bearer <TOKEN>" \
  -F "subject=Ekran çalışmıyor" \
  -F "category_id=1" \
  -F "priority=HIGH" \
  -F "description=Görüntü gidip geliyor" \
  -F "attachments=@/path/screenshot.jpg"
```

#### GET `/Ticket/my-requests`
- **Auth:** **Gerekir**
- **Query:** `page` (default 1), `per_page` (default 10)
- **Açıklama:** Kullanıcının açtığı ticket’ları sayfalı döner. `subject/priority/status` AES çözülerek döner.
- **200 Yanıt (örnek):**
```json
{
  "data": [
    {
      "ticket_id": "#42",
      "subject": "Ekran çalışmıyor",
      "priority": "HIGH",
      "status": "OPEN",
      "category": "category1",
      "update_date": "11.08.2025",
      "created_date": "11.08.2025"
    }
  ],
  "pagination": { "total_items": 5, "page": 1, "per_page": 10, "total_pages": 1 }
}
```

#### GET `/Ticket/{ticket_id}/detail`
- **Auth:** **Gerekir**
- **Açıklama:** Ticket detayını; requester/assignee, CC’ler, followers, mesajlar ve ekleriyle birlikte döner. AES çözümleme yapılır.

#### POST `/Ticket/{ticket_id}/messages`
- **Auth:** **Gerekir**
- **Body (JSON):**
```json
{ "message_text": "Güncelleme var mı?", "is_internal": 0 }
```
- **201 Yanıt:** `{ "message_id": 101 }`  
Mesaj eklendiğinde Ticket `update_date` otomatik güncellenir.

#### PATCH `/Ticket/{ticket_id}`
- **Auth:** **Gerekir**
- **Açıklama:** Ticket alanlarını kısmi günceller (`status`, `priority`, `assigned_user_id`). `status/priority` AES ile şifrelenerek saklanır.
- **Body (JSON, örnek):**
```json
{ "status": "IN_PROGRESS", "priority": "MEDIUM", "assigned_user_id": 7 }
```

#### POST `/Ticket/messages/{message_id}/attachments`
- **Auth:** **Gerekir**
- **Açıklama:** Var olan mesaja dosya ekler (multipart/form-data).
- **Form-Data:** `file=@/path/file.pdf`
- **201 Yanıt:** `{ "status": "ok" }`

#### GET `/Ticket/all-open`
- **Auth:** **Gerekir**
- **Query:** `page`, `per_page`
- **Açıklama:** **Şifreli** `status = OPEN` OLAN **veya** `assigned_user_id IS NULL` olan tüm ticket’ları listeler. AES çözümü ile isimler döner.

#### POST `/Ticket/{ticket_id}/assign`
- **Auth:** **Gerekir**
- **Açıklama:** Ticket'ı çağrıyı yapan kullanıcıya atar (`assigned_user_id = request.user_id`).
- **200 Yanıt:**
```json
{ "message": "Ticket başarıyla atandı", "ticket_id": 42, "assigned_user_id": 7 }
```

---

## Tablo/Model Referansları

Kod tabanında aşağıdaki tablolar kullanılmaktadır (tam şema projede yer alır):
- `TblUser`, `TblAddress`, `TblPhone`, `TblEmail`
- `TblCategory`
- `TblTicket`, `TblTicketMessage`, `TblTicketMessageAttachment`
- `TblTicketCC`, `TblTicketFollower`
- (Klasör/ek dosyalar için) `TblFolder`

Not: İsim, soyisim, iletişim, web/pp görseli gibi alanlar AES ile şifrelenmiş olarak saklanıyor.

---

## Güncelleme Notları

- Bu dokümantasyon doğrudan sağladığın `app.py`, `UserController`, `CategoryController`, `TicketController` dosyalarından türetilmiştir.
- Endpoint parametreleri veya yanıt şemaları değişirse bu dosyayı eşleştirip güncelleyelim.
- İstersen **OpenAPI 3.0 (Swagger)** şeması da üretebilirim.

---

## Lisans

Bu proje sahibine aittir. İzin almadan çoğaltmayınız veya dağıtmayınız.
