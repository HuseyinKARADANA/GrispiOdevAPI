from config import db

class TblEmail(db.Model):
    __tablename__ = "TblEmail"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("TblUser.id"), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Kullanıcıyla ilişki
    user = db.relationship("TblUser", backref=db.backref("emails", lazy=True))
