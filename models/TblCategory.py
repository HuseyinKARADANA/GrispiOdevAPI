from config import db

class TblCategory(db.Model):
    __tablename__ = "TblCategory"

    id = db.Column(db.Integer, primary_key=True)
    category_name = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # Tersten erişim: kategoriye ait tüm ticketlar
    tickets = db.relationship("TblTicket", backref="category", lazy=True)
