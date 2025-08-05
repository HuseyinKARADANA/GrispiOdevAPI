from config import db

class TblFolder(db.Model):
    __tablename__ = "TblFolder"

    id = db.Column(db.Integer, primary_key=True)

    ticket_id = db.Column(db.Integer, db.ForeignKey("TblTicket.TicketId"), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # İlişki: Bir ticket'ın dosyalarına erişim için
    ticket = db.relationship("TblTicket", backref=db.backref("files", lazy=True))
