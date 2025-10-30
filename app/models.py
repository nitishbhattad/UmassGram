from flask_login import UserMixin
from app import login_manager
import MySQLdb.cursors

class User(UserMixin):
    def __init__(self, id, username, email, password):
        self.id = id
        self.username = username
        self.email = email
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    from app import mysql
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    if user:
        return User(user['user_id'], user['username'], user['email'], user['password'])
    return None
