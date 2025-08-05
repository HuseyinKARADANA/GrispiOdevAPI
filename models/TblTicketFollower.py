from config import db

class TblTicketFollower(db.Model):
    __tablename__ = "TblTicketFollower"

    id = db.Column(db.Integer, primary_key=True)

    ticket_id = db.Column(db.Integer, db.ForeignKey("TblTicket.TicketId"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("TblUser.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    # İlişkiler
    ticket = db.relationship("TblTicket", backref=db.backref("followers", lazy=True, cascade="all, delete-orphan"))
    user = db.relationship("TblUser", backref=db.backref("following_tickets", lazy=True))
