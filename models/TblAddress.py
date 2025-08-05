from config import db


class TblAddress(db.Model):
    __tablename__ = "TblAddress"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("TblUser.id"), nullable=False)
    country = db.Column(db.String(128), nullable=True)
    city = db.Column(db.String(128), nullable=True)
    address_line = db.Column(db.String(512), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # İlişki (tersten erişim için)
    user = db.relationship("TblUser", backref=db.backref("addresses", lazy=True))
