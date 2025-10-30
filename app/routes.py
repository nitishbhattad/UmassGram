from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from app.forms import RegisterForm, LoginForm, UploadForm
from app.models import User
from app import mysql
import os
import uuid

main = Blueprint('main', __name__)

@main.route("/")
def home():
    return render_template("home.html")

@main.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()

        if not email.endswith("@umassd.edu"):
            flash("Only UMass email addresses are allowed to register.", "danger")
            return redirect(url_for("main.register"))

        # Check if username already exists
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (form.username.data,))
        if cur.fetchone():
            flash("Username already exists", "danger")
            return redirect(url_for("main.register"))

        hashed_pw = generate_password_hash(form.password.data)
        cur.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                    (form.username.data, email, hashed_pw))
        mysql.connection.commit()
        cur.close()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("main.login"))
    return render_template("register.html", form=form)


@main.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s", (form.username.data,))
        user = cur.fetchone()
        cur.close()

        if user and check_password_hash(user['password'], form.password.data):
            login_user(User(user['user_id'], user['username'], user['email'], user['password']))
            return redirect(url_for('main.feed'))
        else:
            flash("Invalid username or password", "danger")
    return render_template("login.html", form=form)


@main.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for('main.home'))  # 👈 better than going directly to login


@main.route("/feed")
@login_required
def feed():
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT posts.*, users.username,
            (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.post_id) AS like_count,
            (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.post_id AND likes.user_id = %s) AS user_liked,
            (SELECT COUNT(*) FROM followers WHERE follower_id = %s AND following_id = posts.user_id) AS is_following,
            (SELECT COUNT(*) FROM saved_posts WHERE saved_posts.user_id = %s AND saved_posts.post_id = posts.post_id) AS is_saved,
            (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.post_id) AS comment_count
        FROM posts
        JOIN users ON posts.user_id = users.user_id
        ORDER BY posts.created_at DESC
    """, (current_user.id, current_user.id, current_user.id))
    posts = cur.fetchall()

    cur.execute("""
        SELECT comments.*, users.username
        FROM comments
        JOIN users ON comments.user_id = users.user_id
        ORDER BY comments.created_at ASC
    """)
    comments = cur.fetchall()

    cur.execute("""
    SELECT feedback.*, users.username
    FROM feedback
    JOIN users ON feedback.sender_id = users.user_id
    WHERE feedback.post_id IN (
        SELECT post_id FROM posts WHERE user_id = %s
    )
    ORDER BY feedback.created_at ASC
""", (current_user.id,))
    feedbacks = cur.fetchall()


    cur.close()

    return render_template("feed.html", posts=posts, comments=comments, feedbacks=feedbacks)






@main.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        image = form.image.data
        if image is None or image.filename == "":
            flash("Please select an image to upload.", "danger")
            return redirect(url_for('main.upload'))

        filename = secure_filename(str(uuid.uuid4()) + "_" + image.filename)
        upload_folder = os.path.join('app', 'static', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        upload_path = os.path.join(upload_folder, filename)
        image.save(upload_path)

        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO posts (user_id, image_path, caption) VALUES (%s, %s, %s)",
                    (current_user.id, filename, form.caption.data))
        mysql.connection.commit()
        cur.close()
        flash("Post uploaded!", "success")
        return redirect(url_for('main.feed'))
    return render_template("upload.html", form=form)

@main.route("/like/<int:post_id>", methods=["POST"])
@login_required
def like(post_id):
    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM likes WHERE user_id = %s AND post_id = %s", (current_user.id, post_id))
    existing_like = cur.fetchone()

    if existing_like:
        # Unlike
        cur.execute("DELETE FROM likes WHERE user_id = %s AND post_id = %s", (current_user.id, post_id))
    else:
        # Like
        cur.execute("INSERT INTO likes (user_id, post_id) VALUES (%s, %s)", (current_user.id, post_id))

        #  Notification of likes
        cur.execute("SELECT user_id FROM posts WHERE post_id = %s", (post_id,))
        owner = cur.fetchone()

        if owner and owner['user_id'] != current_user.id:
            cur.execute("""
                INSERT INTO notifications (recipient_id, sender_id, post_id, type)
                VALUES (%s, %s, %s, 'like')
            """, (owner['user_id'], current_user.id, post_id))

    mysql.connection.commit()
    cur.close()
    return redirect(url_for('main.feed'))


@main.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def comment(post_id):
    content = request.form.get('comment')
    if content:
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO comments (user_id, post_id, content) VALUES (%s, %s, %s)",
                    (current_user.id, post_id, content))
        # Notify post owner (if not the one commenting)
        cur.execute("SELECT user_id FROM posts WHERE post_id = %s", (post_id,))
        owner = cur.fetchone()

    if owner and owner['user_id'] != current_user.id:
        cur.execute("""
        INSERT INTO notifications (recipient_id, sender_id, post_id, type)
        VALUES (%s, %s, %s, 'comment')
    """, (owner['user_id'], current_user.id, post_id))

        mysql.connection.commit()
        cur.close()
    return redirect(url_for('main.feed'))

@main.route('/follow/<int:user_id>', methods=['POST'])
@login_required
def follow(user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM followers WHERE follower_id = %s AND following_id = %s",
                (current_user.id, user_id))
    existing = cur.fetchone()

    if existing:
        cur.execute("DELETE FROM followers WHERE follower_id = %s AND following_id = %s",
                    (current_user.id, user_id))  # Unfollow
    else:
        cur.execute("INSERT INTO followers (follower_id, following_id) VALUES (%s, %s)",
                    (current_user.id, user_id))  # Follow
        # Add follow notification
    cur.execute("""
    INSERT INTO notifications (recipient_id, sender_id, type)
    VALUES (%s, %s, 'follow')
""", (user_id, current_user.id))

    
    mysql.connection.commit()
    cur.close()
    return redirect(url_for('main.feed'))

@main.route('/save/<int:post_id>', methods=['POST'])
@login_required
def save_post(post_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM saved_posts WHERE user_id = %s AND post_id = %s", (current_user.id, post_id))
    existing = cur.fetchone()

    if existing:
        cur.execute("DELETE FROM saved_posts WHERE user_id = %s AND post_id = %s", (current_user.id, post_id))
    else:
        cur.execute("INSERT INTO saved_posts (user_id, post_id) VALUES (%s, %s)", (current_user.id, post_id))

    mysql.connection.commit()
    cur.close()
    return redirect(url_for('main.feed'))
@main.route("/explore")
@login_required
def explore():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT posts.*, users.username FROM posts
        JOIN users ON posts.user_id = users.user_id
        ORDER BY RAND()
    """)
    posts = cur.fetchall()
    cur.close()
    return render_template("explore.html", posts=posts)

@main.route('/saved')
@login_required
def saved_posts():
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT posts.*, users.username
        FROM saved_posts
        JOIN posts ON saved_posts.post_id = posts.post_id
        JOIN users ON posts.user_id = users.user_id
        WHERE saved_posts.user_id = %s
        ORDER BY saved_posts.created_at DESC
    """, (current_user.id,))
    posts = cur.fetchall()
    cur.close()

    return render_template("saved.html", posts=posts)

@main.route('/profile/<username>')
@login_required
def profile(username):
    cur = mysql.connection.cursor()

    # Get user details
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('main.feed'))

    # Follower count
    cur.execute("SELECT COUNT(*) AS count FROM followers WHERE following_id = %s", (user['user_id'],))
    followers = cur.fetchone()['count']

    # Following count
    cur.execute("SELECT COUNT(*) AS count FROM followers WHERE follower_id = %s", (user['user_id'],))
    following = cur.fetchone()['count']

    # Get list of followers
    cur.execute("""
        SELECT users.username FROM followers
        JOIN users ON followers.follower_id = users.user_id
        WHERE followers.following_id = %s
    """, (user['user_id'],))
    follower_list = cur.fetchall()

    # Get list of following
    cur.execute("""
        SELECT users.username FROM followers
        JOIN users ON followers.following_id = users.user_id
        WHERE followers.follower_id = %s
    """, (user['user_id'],))
    following_list = cur.fetchall()

    cur.close()

    return render_template("profile.html", user=user, followers=followers, following=following,
                           follower_list=follower_list, following_list=following_list)
import os

@main.route('/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    cur = mysql.connection.cursor()

    # Ensure the post belongs to the user
    cur.execute("SELECT * FROM posts WHERE post_id = %s AND user_id = %s", (post_id, current_user.id))
    post = cur.fetchone()

    if not post:
        flash("Post not found or you're not authorized to delete it.", "danger")
        return redirect(url_for('main.feed'))

    # Delete related likes, comments, and saved posts
    cur.execute("DELETE FROM likes WHERE post_id = %s", (post_id,))
    cur.execute("DELETE FROM comments WHERE post_id = %s", (post_id,))
    cur.execute("DELETE FROM saved_posts WHERE post_id = %s", (post_id,))

    # Delete image file from disk
    image_path = os.path.join('app', 'static', 'uploads', post['image_path'])
    if os.path.exists(image_path):
        os.remove(image_path)

    # Delete the post itself
    cur.execute("DELETE FROM posts WHERE post_id = %s", (post_id,))
    mysql.connection.commit()
    cur.close()

    flash("Post and all related data deleted successfully.", "success")
    return redirect(url_for('main.feed'))

@main.route("/notifications")
@login_required
def notifications():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT n.*, u.username AS sender_name, p.caption
        FROM notifications n
        LEFT JOIN users u ON n.sender_id = u.user_id
        LEFT JOIN posts p ON n.post_id = p.post_id
        WHERE n.recipient_id = %s
        ORDER BY n.created_at DESC
    """, (current_user.id,))
    notes = cur.fetchall()
    cur.close()
    return render_template("notifications.html", notifications=notes)

@main.route('/feedback/<int:post_id>', methods=['POST'])
@login_required
def feedback(post_id):
    content = request.form.get('feedback')
    if content:
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO feedback (post_id, sender_id, content)
            VALUES (%s, %s, %s)
        """, (post_id, current_user.id, content))
        mysql.connection.commit()
        cur.close()
        flash("Anonymous feedback sent!", "success")
    return redirect(url_for('main.feed'))

@main.route("/me")
@login_required
def self_profile():
    cur = mysql.connection.cursor()

    # Count followers with alias
    cur.execute("SELECT COUNT(*) AS count FROM followers WHERE following_id = %s", (current_user.id,))
    followers_result = cur.fetchone()
    followers = followers_result['count'] if followers_result and 'count' in followers_result else 0

    # Count following with alias
    cur.execute("SELECT COUNT(*) AS count FROM followers WHERE follower_id = %s", (current_user.id,))
    following_result = cur.fetchone()
    following = following_result['count'] if following_result and 'count' in following_result else 0

    # Get current user's posts
    cur.execute("SELECT * FROM posts WHERE user_id = %s ORDER BY created_at DESC", (current_user.id,))
    posts = cur.fetchall()

    cur.close()

    return render_template(
        "self_profile.html",
        username=current_user.username,
        email=current_user.email,
        user_id=current_user.id,
        followers=followers,
        following=following,
        posts=posts
    )








