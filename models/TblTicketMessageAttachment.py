from config import db


class TblTicketMessageAttachment(db.Model):
    __tablename__ = "TblTicketMessageAttachment"

    id = db.Column(db.Integer, primary_key=True)

    message_id = db.Column(db.Integer, db.ForeignKey("TblTicketMessage.id"), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # İlişki
    message = db.relationship("TblTicketMessage",
                              backref=db.backref("attachments", lazy=True, cascade="all, delete-orphan"))
