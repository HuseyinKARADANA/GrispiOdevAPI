from flask import Flask
from flask_cors import CORS
from config import db, DATABASE_URI
from flask_migrate import Migrate

from models.TblUser import TblUser
from models.TblAddress import TblAddress
from models.TblTicket import TblTicket
from models.TblTicketMessage import TblTicketMessage
from models.TblTicketMessageAttachment import TblTicketMessageAttachment
from models.TblFolder import TblFolder
from models.TblCategory import TblCategory
from models.TblPhone import TblPhone
from models.TblEmail import TblEmail
from models.TblTicketCC import TblTicketCC
from models.TblTicketFollower import TblTicketFollower


from controllers.UserController import user_controller




app = Flask(__name__)
CORS(app)

migrate =Migrate(app,db)




app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db.init_app(app)

app.register_blueprint(user_controller,url_prefix='/User')



@app.route('/')
def home():
    return "Flask API Çalışıyor!", 200

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8006)
