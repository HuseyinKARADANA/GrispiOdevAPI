from config import db


class TblPhone(db.Model):
    __tablename__ = "TblPhone"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("TblUser.id"), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # İlişki: Kullanıcıya geri erişim
    user = db.relationship("TblUser", backref=db.backref("phones", lazy=True))
