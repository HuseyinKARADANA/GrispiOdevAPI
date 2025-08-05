import os
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from dotenv import load_dotenv
load_dotenv()  # .env dosyasını yükler


# 32 byte = 256-bit key (AES256)
SECRET_KEY = os.environ.get("AES_SECRET_KEY").encode()

# Sabit IV (16 byte)
STATIC_IV = os.environ.get("AES_STATIC_IV").encode()

class AESService:
    @staticmethod
    def encrypt(plaintext: str) -> str:
        """
        Deterministic AES CBC şifreleme (sabit IV kullanır).
        Aynı metin her şifrelemede aynı çıktıyı üretir.
        """
        cipher = AES.new(SECRET_KEY, AES.MODE_CBC, STATIC_IV)
        ct_bytes = cipher.encrypt(pad(plaintext.encode('utf-8'), AES.block_size))
        return base64.b64encode(ct_bytes).decode('utf-8')

    @staticmethod
    def decrypt(enc_data: str) -> str:
        """
        Deterministic AES CBC çözme.
        """
        ct = base64.b64decode(enc_data)
        cipher = AES.new(SECRET_KEY, AES.MODE_CBC, STATIC_IV)
        pt = unpad(cipher.decrypt(ct), AES.block_size)
        return pt.decode('utf-8')
