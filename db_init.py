from app import app
from config import db
import logging
from sqlalchemy.exc import SQLAlchemyError

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

try:
    with app.app_context():
        # Veritabanı bağlantısını test et
        db.engine.connect()
        logger.info("Veritabanı bağlantısı başarılı!")

        # Tabloları oluştur
        db.create_all()
        logger.info("Veritabanı tabloları başarıyla oluşturuldu!")


except SQLAlchemyError as e:
    logger.error(f"Veritabanı hatası: {str(e)}")
    raise
except Exception as e:
    logger.error(f"Beklenmeyen hata: {str(e)}")
    raise
