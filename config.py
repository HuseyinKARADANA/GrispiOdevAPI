from flask_sqlalchemy import SQLAlchemy
from urllib.parse import quote_plus

password = quote_plus("fZ@Yy3bYfzlv1i*3")  # ? karakteri encode ediliyor

DATABASE_URI = (
    f"mssql+pyodbc://huseyi98_odevAdmin:{password}"
    "@104.247.167.130\\mssqlserver2022"
    "/huseyi98_GrispiOdev1"
    "?driver=ODBC+Driver+17+for+SQL+Server"
    "&TrustServerCertificate=yes"
    "&Encrypt=yes"
)

db = SQLAlchemy()
