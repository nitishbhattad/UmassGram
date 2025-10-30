from flask import Flask
from flask_login import LoginManager
from flask_mysqldb import MySQL
import os

mysql = MySQL()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'umassgram_secret_key'
    app.config['UPLOAD_FOLDER'] = os.path.join('app', 'static', 'uploads')
    app.config['MYSQL_HOST'] = 'localhost'
    app.config['MYSQL_USER'] = 'root'
    app.config['MYSQL_PASSWORD'] = 'nitish@9019'
    app.config['MYSQL_DB'] = 'umassgram'
    app.config['MYSQL_CURSORCLASS'] = 'DictCursor'


    mysql.init_app(app)
    login_manager.init_app(app)

    from app.routes import main
    app.register_blueprint(main)

    return app
