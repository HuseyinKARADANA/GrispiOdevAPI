from config import db

class TblTicketCC(db.Model):
    __tablename__ = "TblTicketCC"

    id = db.Column(db.Integer, primary_key=True)

    ticket_id = db.Column(db.Integer, db.ForeignKey("TblTicket.TicketId"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("TblUser.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # İlişkiler
    ticket = db.relationship("TblTicket", backref=db.backref("cc_users", lazy=True, cascade="all, delete-orphan"))
    user = db.relationship("TblUser", backref=db.backref("cc_tickets", lazy=True))
