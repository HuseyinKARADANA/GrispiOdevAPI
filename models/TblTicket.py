from config import db


class TblTicket(db.Model):
    __tablename__ = "TblTicket"

    TicketId = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("TblUser.id"), nullable=False)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey("TblUser.id"), nullable=True)

    subject = db.Column(db.String(1024), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("TblCategory.id"), nullable=False)
    description = db.Column(db.Text, nullable=True)
    priority = db.Column(db.String(50), nullable=False, default="LOW")  # LOW, MEDIUM, HIGH gibi
    status = db.Column(db.String(50), nullable=False, default="OPEN")  # OPEN, CLOSED, PENDING gibi

    update_date = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())
    created_date = db.Column(db.DateTime, default=db.func.current_timestamp())

    # İlişkiler
    user = db.relationship("TblUser", foreign_keys=[user_id], backref=db.backref("created_tickets", lazy=True))
    assigned_user = db.relationship("TblUser", foreign_keys=[assigned_user_id],
                                    backref=db.backref("assigned_tickets", lazy=True))
    category = db.relationship("TblCategory", backref=db.backref("tickets", lazy=True))
