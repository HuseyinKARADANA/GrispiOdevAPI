from config import db


class TblUser(db.Model):
    __tablename__ = "TblUser"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(1024), nullable=False)
    surname = db.Column(db.String(1024), nullable=False)

    preliminary_phone = db.Column(db.String(512), nullable=True)
    preliminary_email = db.Column(db.String(1024), nullable=True)

    password = db.Column(db.String(1024), nullable=False)  # password_hash yerine birebir eşleşme

    role = db.Column(db.String(128), nullable=False)
    profile_img = db.Column(db.String(1024), nullable=True)
    website = db.Column(db.String(1024), nullable=True)

    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    grispiId=db.Column(db.Integer, nullable=True)
