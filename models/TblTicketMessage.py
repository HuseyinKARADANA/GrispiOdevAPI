from config import db


class TblTicketMessage(db.Model):
    __tablename__ = "TblTicketMessage"

    id = db.Column(db.Integer, primary_key=True)

    ticket_id = db.Column(db.Integer, db.ForeignKey("TblTicket.TicketId"), nullable=False)
    sender_user_id = db.Column(db.Integer, db.ForeignKey("TblUser.id"), nullable=False)

    message_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    is_internal = db.Column(db.Boolean, default=False, nullable=False)

    # İlişkiler
    ticket = db.relationship("TblTicket", backref=db.backref("messages", lazy=True, cascade="all, delete-orphan"))
    sender = db.relationship("TblUser", backref=db.backref("sent_messages", lazy=True))
