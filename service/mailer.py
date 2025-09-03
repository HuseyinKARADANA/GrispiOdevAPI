"""
mailer.py
---------
Basit kullanım için fonksiyon odaklı e-posta yardımcıları.
mail_service.MailService üzerine ince bir sarmalayıcı.

Kurulum:
- Ortam değişkenlerini ayarlayın (ya da SMTP_* sabitlerini düzenleyin).
- Projende `from mailer import send_welcome_email` gibi kullan.

Örnek:
send_welcome_email("kullanici@ornek.com", "Ömer")
"""

import os
from typing import Optional, Sequence
from .mail_service import MailService

# ---- SMTP Ayarları (ENV ile veya sabitle) ----
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.example.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "no-reply@example.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "password")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() in ("1", "true", "yes")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Bildirim Botu")

# ---- Marka ayarları (ENV ile override edilebilir) ----
BRAND_NAME       = os.getenv("BRAND_NAME", "Grispi")
BRAND_PRIMARY    = os.getenv("BRAND_PRIMARY", "#6B3DF0")   # mor
BRAND_TEXT       = os.getenv("BRAND_TEXT", "#2B2B2B")
BRAND_BG         = os.getenv("BRAND_BG", "#F6F7FB")
BRAND_CARD_BG    = os.getenv("BRAND_CARD_BG", "#FFFFFF")
BRAND_BORDER     = os.getenv("BRAND_BORDER", "#ECECF1")
BRAND_LOGO_URL   = os.getenv("BRAND_LOGO_URL", "https://i.hizliresim.com/2lg5ymb.jpg")
TICKET_PORTAL_URL= os.getenv("TICKET_PORTAL_URL", "https://grispi.com/tr/")     # örn: https://portal.domain.com/tickets/{ticket_no}


# Tek seferlik servis nesnesi
_svc = MailService(
    host=SMTP_HOST,
    port=SMTP_PORT,
    username=SMTP_USERNAME,
    password=SMTP_PASSWORD,
    use_tls=SMTP_USE_TLS,
    use_ssl=SMTP_USE_SSL,
    default_from=SMTP_FROM,
    default_from_name=SMTP_FROM_NAME,
    retries=1,
)


def _send(to: Sequence[str] | str, subject: str, text: str, html: Optional[str] = None) -> bool:
    ok, info = _svc.send_email(
        to=to,
        subject=subject,
        text=text,
        html=html,
    )
    if not ok:
        print(f"E-posta gönderilemedi: {info}")
    return ok


# ---------------- Hazır Fonksiyonlar ----------------

def send_welcome_email(email: str, name: str) -> bool:
    """
    Basit hoş geldin e-postası.
    """
    subject = "Aramıza Hoş Geldin!"
    text = f"Merhaba {name},\n\nAramıza hoş geldin. Hesabın başarıyla oluşturuldu.\nİyi kullanımlar!"
    html = f"""
    <h2>Merhaba {name},</h2>
    <p>Aramıza <b>hoş geldin</b>! Hesabın başarıyla oluşturuldu.</p>
    <p>İyi kullanımlar.</p>
    """
    try:
        return _send(email, subject, text, html)
    except Exception as e:
        print(f"Hoş geldin maili gönderilemedi: {e}")
        return False



def send_ticket_opened_email(email: str, ticket_no: str, title: str) -> bool:
    """
    Destek talebi oluşturuldu bildirimi (tasarımlı HTML şablon).
    """
    subject = f"Talebin Alındı #{ticket_no}"

    # Düz metin fallback (tüm istemcilerde güvenli)
    text = (
        f"Merhaba,\n\n"
        f"#{ticket_no} numaralı '{title}' başlıklı talebin alındı.\n"
        f"En kısa sürede dönüş yapacağız.\n"
        + (f"\nTalebi görüntüle: {TICKET_PORTAL_URL.format(ticket_no=ticket_no)}\n" if TICKET_PORTAL_URL else "")
        + "\n— {brand}".format(brand=BRAND_NAME)
    )

    # HTML şablon (inline CSS — e-posta uyumlu)
    portal_href = (TICKET_PORTAL_URL or "").format(ticket_no=ticket_no) if TICKET_PORTAL_URL else ""
    cta_html = (
        f'''<a href="{portal_href}" target="_blank"
            style="background:{BRAND_PRIMARY};color:#fff;text-decoration:none;
                   display:inline-block;padding:12px 20px;border-radius:8px;
                   font-weight:600">Talebi Görüntüle</a>'''
        if portal_href else ""
    )

    html = f"""
<!DOCTYPE html>
<html lang="tr">
  <body style="margin:0;padding:0;background:{BRAND_BG};">
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background:{BRAND_BG};padding:24px 0;">
      <tr>
        <td align="center">
          <!-- Card -->
          <table width="640" cellpadding="0" cellspacing="0" role="presentation"
                 style="max-width:640px;width:100%;background:{BRAND_CARD_BG};border:1px solid {BRAND_BORDER};
                        border-radius:16px;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:{BRAND_TEXT}">
            <!-- Header / Logo -->
            <tr>
              <td align="center" style="padding:28px 24px 8px 24px;">
                <img src="{BRAND_LOGO_URL}" width="48" height="48" alt="{BRAND_NAME} logo"
                     style="display:block;border:0;outline:none;"/>
                <div style="font-size:14px;color:#6b7280;margin-top:8px;letter-spacing:.4px">{BRAND_NAME}</div>
              </td>
            </tr>

            <!-- Title -->
            <tr>
              <td style="padding:8px 32px 0 32px;">
                <h1 style="margin:0;font-size:20px;line-height:28px;color:{BRAND_TEXT};">
                  Talebin Alındı <span style="color:{BRAND_PRIMARY}">#{ticket_no}</span>
                </h1>
              </td>
            </tr>

            <!-- Intro text -->
            <tr>
              <td style="padding:12px 32px 8px 32px;font-size:14px;line-height:22px;color:{BRAND_TEXT}">
                Merhaba,<br/>
                <strong>“{title}”</strong> başlıklı talebin başarıyla oluşturuldu.
                En kısa sürede dönüş yapacağız.
              </td>
            </tr>

            <!-- Details -->
            <tr>
              <td style="padding:8px 32px 16px 32px;">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                       style="border-collapse:separate;border-spacing:0 8px;">
                  <tr>
                    <td width="140" style="font-size:12px;color:#6b7280;">Talep No</td>
                    <td style="font-size:14px;color:{BRAND_TEXT};font-weight:600;">#{ticket_no}</td>
                  </tr>
                  <tr>
                    <td width="140" style="font-size:12px;color:#6b7280;">Başlık</td>
                    <td style="font-size:14px;color:{BRAND_TEXT};">{title}</td>
                  </tr>
                  <tr>
                    <td width="140" style="font-size:12px;color:#6b7280;">Durum</td>
                    <td style="font-size:14px;color:{BRAND_TEXT};">OPEN</td>
                  </tr>
                </table>
              </td>
            </tr>

            <!-- CTA -->
            {"<tr><td align='left' style='padding:8px 32px 24px 32px;'>"+cta_html+"</td></tr>" if cta_html else ""}

            <!-- Footer -->
            <tr>
              <td style="padding:20px 32px 28px 32px;font-size:12px;color:#6b7280;border-top:1px solid {BRAND_BORDER}">
                Bu e-posta {BRAND_NAME} tarafından gönderildi. Bu mesajı beklemiyor muydun? Lütfen destek ekibiyle iletişime geç.
              </td>
            </tr>
          </table>
          <!-- /Card -->
        </td>
      </tr>
    </table>
  </body>
</html>
    """

    try:
        return _send(email, subject, text, html)
    except Exception as e:
        print(f"Talep açılış maili gönderilemedi: {e}")
        return False


def send_password_reset_email(email: str, reset_link: str) -> bool:
    """
    Şifre sıfırlama bağlantısı.
    """
    subject = "Şifre Sıfırlama Talebin"
    text = (
        "Merhaba,\n\nŞifre sıfırlamak için aşağıdaki bağlantıyı kullan:\n"
        f"{reset_link}\n\nBu talebi sen yapmadıysan bu e-postayı yok sayabilirsin."
    )
    html = f"""
    <h3>Şifre Sıfırlama</h3>
    <p>Aşağıdaki bağlantıya tıklayarak şifreni sıfırlayabilirsin:</p>
    <p><a href="{reset_link}">{reset_link}</a></p>
    <p>Bu talebi sen yapmadıysan yok sayabilirsin.</p>
    """
    try:
        return _send(email, subject, text, html)
    except Exception as e:
        print(f"Şifre sıfırlama maili gönderilemedi: {e}")
        return False


def send_otp_email(email: str, otp_code: str, minutes_valid: int = 5) -> bool:
    """
    Tek kullanımlık doğrulama kodu.
    """
    subject = "Doğrulama Kodun"
    text = (
        f"Merhaba,\n\nDoğrulama kodun: {otp_code}\n"
        f"Bu kod {minutes_valid} dakika boyunca geçerlidir."
    )
    html = f"""
    <h3>Doğrulama Kodun</h3>
    <p><b>{otp_code}</b></p>
    <p>Bu kod {minutes_valid} dakika boyunca geçerlidir.</p>
    """
    try:
        return _send(email, subject, text, html)
    except Exception as e:
        print(f"OTP maili gönderilemedi: {e}")
        return False


def send_generic_email(email: str, subject: str, text: str, html: Optional[str] = None) -> bool:
    """
    Her türlü basit gönderim için genel fonksiyon.
    """
    try:
        return _send(email, subject, text, html)
    except Exception as e:
        print(f"Genel e-posta gönderilemedi: {e}")
        return False


# Hızlı manuel test
if __name__ == "__main__":
    # Örnek kullanım
    send_welcome_email("test@example.com", "Ömer")
