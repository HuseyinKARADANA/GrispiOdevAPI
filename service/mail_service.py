"""
mail_service.py
----------------
Basit ama üretim ortamına uygun bir SMTP e‑posta servis sınıfı.

Öne çıkanlar
- TLS/SSL desteği
- HTML + düz metin (multipart/alternative)
- CC / BCC / Reply-To
- Dosya eki (path ya da (filename, bytes, mime_type))
- Zaman aşımı, yeniden deneme (retry) ve üstel geri çekilme (exponential backoff)
- Tip ipuçları ve ayrıntılı dokümantasyon

Kullanım
--------
from mail_service import MailService
svc = MailService(
    host="smtp.example.com",
    port=587,
    username="no-reply@example.com",
    password="***",
    use_tls=True,
    default_from="no-reply@example.com",
    default_from_name="YükRadar"
)

svc.send_email(
    to=["alici@example.com"],
    subject="Merhaba",
    text="Düz metin gövdesi",
    html="<h1>Merhaba</h1><p>HTML gövdesi</p>",
    attachments=["/path/to/file.pdf"]
)

Ortam değişkenleri ile örnek kullanım için dosyanın en altındaki __main__ örneğine bakın.
"""

from __future__ import annotations

import os
import smtplib
import ssl
import time
import mimetypes
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union, Dict

from email.message import EmailMessage
from email.utils import formatdate, make_msgid


AttachmentType = Union[str, Path, Tuple[str, bytes, str]]  # path  veya (filename, bytes, mime_type)


class MailService:
    """
    SMTP üzerinden e‑posta göndermek için basit servis.

    Parametreler
    ------------
    host : str
        SMTP sunucu adresi, örn. "smtp.gmail.com"
    port : int
        SMTP portu (TLS için genellikle 587, SSL için 465)
    username : Optional[str]
        SMTP kullanıcı adı (gerekmiyorsa None bırakın)
    password : Optional[str]
        SMTP şifresi (gerekmiyorsa None bırakın)
    use_tls : bool
        STARTTLS kullan (default: True)
    use_ssl : bool
        Doğrudan SMTPS (SSL) kullan (default: False)
    timeout : int
        Sunucu ile soket zaman aşımı (saniye)
    default_from : Optional[str]
        Varsayılan gönderici e‑posta adresi
    default_from_name : Optional[str]
        Varsayılan görünen ad
    retries : int
        Başarısız denemelerde yeniden deneme sayısı
    backoff : float
        Yeniden denemeler arası çarpan (örn. 1.5 => 1s, 1.5s, 2.25s)
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        *,
        use_tls: bool = True,
        use_ssl: bool = False,
        timeout: int = 30,
        default_from: Optional[str] = None,
        default_from_name: Optional[str] = None,
        retries: int = 2,
        backoff: float = 1.5,
    ) -> None:
        if use_tls and use_ssl:
            raise ValueError("use_tls ve use_ssl aynı anda True olamaz.")
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.use_ssl = use_ssl
        self.timeout = timeout
        self.default_from = default_from
        self.default_from_name = default_from_name
        self.retries = max(0, retries)
        self.backoff = max(1.0, backoff)

    # ------------- Public API -------------

    def send_email(
        self,
        *,
        to: Union[str, Sequence[str]],
        subject: str,
        text: Optional[str] = None,
        html: Optional[str] = None,
        cc: Optional[Sequence[str]] = None,
        bcc: Optional[Sequence[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[Sequence[AttachmentType]] = None,
        headers: Optional[Dict[str, str]] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        E‑posta gönderir.

        Dönüş
        -----
        (success, message_id_or_error) : Tuple[bool, str]
        """
        if not (text or html):
            raise ValueError("En azından 'text' veya 'html' içeriği sağlamalısınız.")

        recipients = _as_list(to) + _as_list(cc) + _as_list(bcc)
        if not recipients:
            raise ValueError("'to/cc/bcc' alanlarından en az biri gerekli.")

        msg = self._build_message(
            to=_as_list(to),
            subject=subject,
            text=text,
            html=html,
            cc=_as_list(cc),
            bcc=_as_list(bcc),
            reply_to=reply_to,
            attachments=attachments or [],
            headers=headers or {},
            from_email=from_email or self.default_from or self.username,
            from_name=from_name or self.default_from_name,
            message_id=message_id,
        )

        attempt = 0
        delay = 1.0
        last_error = None

        while attempt <= self.retries:
            try:
                self._send_via_smtp(msg, recipients)
                return True, msg["Message-Id"]
            except Exception as exc:  # geniş tut: farklı SMTPException tipleri olabilir
                last_error = str(exc)
                attempt += 1
                if attempt > self.retries:
                    break
                time.sleep(delay)
                delay *= self.backoff

        return False, last_error or "Bilinmeyen hata"

    # ------------- Internal helpers -------------

    def _build_message(
        self,
        *,
        to: Sequence[str],
        subject: str,
        text: Optional[str],
        html: Optional[str],
        cc: Sequence[str],
        bcc: Sequence[str],
        reply_to: Optional[str],
        attachments: Sequence[AttachmentType],
        headers: Dict[str, str],
        from_email: Optional[str],
        from_name: Optional[str],
        message_id: Optional[str],
    ) -> EmailMessage:
        msg = EmailMessage()

        # From
        if not from_email:
            raise ValueError("Gönderici adresi (from) belirlenmeli (default_from ya da username kullanın).")
        if from_name:
            msg["From"] = f"{from_name} <{from_email}>"
        else:
            msg["From"] = from_email

        # To / CC
        if to:
            msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)

        # Subject / Date / Message-Id
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-Id"] = message_id or make_msgid(domain=_extract_domain(from_email))

        if reply_to:
            msg["Reply-To"] = reply_to

        # Extra headers
        for k, v in headers.items():
            if k.lower() in {"to", "from", "cc", "bcc", "subject", "date", "message-id"}:
                continue
            msg[k] = v

        # Body (multipart/alternative)
        if html and text:
            msg.set_content(text)
            msg.add_alternative(html, subtype="html")
        elif html:
            # HTML varsa düz metin fallback de eklemek iyi bir pratik
            msg.set_content(_html_to_plain_fallback(html))
            msg.add_alternative(html, subtype="html")
        else:
            msg.set_content(text or "")

        # Attachments
        for att in attachments:
            self._attach(msg, att)

        # BCC as a header'a eklenmez; SMTP envelope içinde gönderilecektir
        return msg

    def _attach(self, msg: EmailMessage, att: AttachmentType) -> None:
        if isinstance(att, (str, Path)):
            p = Path(att)
            if not p.exists() or not p.is_file():
                raise FileNotFoundError(f"Eki bulamadım: {p}")
            ctype, encoding = mimetypes.guess_type(str(p))
            maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
            with open(p, "rb") as f:
                data = f.read()
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=p.name)
        else:
            filename, data, mime = att
            maintype, subtype = (mime or "application/octet-stream").split("/", 1)
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    def _send_via_smtp(self, msg: EmailMessage, recipients: Sequence[str]) -> None:
        context = ssl.create_default_context()
        if self.use_ssl:
            server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)

        try:
            server.ehlo()
            if self.use_tls and not self.use_ssl:
                server.starttls(context=context)
                server.ehlo()

            if self.username and self.password:
                server.login(self.username, self.password)

            server.send_message(msg, to_addrs=list(dict.fromkeys(recipients)))  # uniq yap
        finally:
            try:
                server.quit()
            except Exception:
                # Bağlantı zaten kapanmış olabilir
                pass


# ------------- Utilities -------------

def _as_list(value: Optional[Union[str, Iterable[str]]]) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    # Trim + boşları çıkar
    return [v.strip() for v in value if v and v.strip()]


def _extract_domain(email_addr: str) -> str:
    try:
        return email_addr.split("@", 1)[1]
    except Exception:
        return "localdomain"


def _html_to_plain_fallback(html: str) -> str:
    """
    Minimum düzeyde bir HTML -> text fallback (etiketleri basitçe siler).
    Gelişmiş dönüşüm gerekiyorsa 'html2text' gibi bir kütüphane kullanın.
    """
    import re
    text = re.sub(r"<\s*br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


# ------------- Example (__main__) -------------

if __name__ == "__main__":
    # Ortam değişkenlerinden basit demo
    # Uyarı: Gmail/Outlook gibi servislerde uygulama şifresi gerekebilir.
    host = os.getenv("SMTP_HOST", "smtp.example.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "no-reply@example.com")
    password = os.getenv("SMTP_PASSWORD", "password")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in ("1", "true", "yes")
    default_from = os.getenv("SMTP_FROM", username)
    default_from_name = os.getenv("SMTP_FROM_NAME", "Mail Bot")

    svc = MailService(
        host=host,
        port=port,
        username=username,
        password=password,
        use_tls=use_tls,
        use_ssl=use_ssl,
        default_from=default_from,
        default_from_name=default_from_name,
    )

    ok, info = svc.send_email(
        to=os.getenv("TEST_TO", username),
        subject="MailService Test",
        text="Bu bir test e-postasıdır (düz metin).",
        html="<h3>MailService Test</h3><p>Bu bir <b>HTML</b> test mailidir.</p>",
    )

    print("Gönderim sonucu:", ok, "| Message-ID/Hata:", info)
