from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, session, flash
from PIL import Image, UnidentifiedImageError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import RequestEntityTooLarge
import sqlite3
from functools import wraps
from pathlib import Path
from uuid import uuid4
import warnings

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-deployment"
DB_PATH = Path(__file__).with_name("books.db")
UPLOAD_FOLDER = Path(__file__).with_name("static") / "uploads"
MAX_IMAGE_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_UPLOAD_BYTES + 1024 * 1024

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            subject TEXT NOT NULL,
            semester TEXT NOT NULL,
            condition TEXT NOT NULL,
            book_type TEXT NOT NULL CHECK(book_type IN ('Exchange','Donation')),
            description TEXT DEFAULT '',
            image_filename TEXT,
            status TEXT NOT NULL DEFAULT 'Available',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(owner_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS book_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            requester_id INTEGER NOT NULL,
            message TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(book_id) REFERENCES books(id),
            FOREIGN KEY(requester_id) REFERENCES users(id)
        );
        """)
        book_columns = {row["name"] for row in db.execute("PRAGMA table_info(books)")}
        if "image_filename" not in book_columns:
            db.execute("ALTER TABLE books ADD COLUMN image_filename TEXT")
init_db()

def prepare_book_image(upload):
    if not upload or not upload.filename:
        return None

    data = upload.stream.read(MAX_IMAGE_UPLOAD_BYTES + 1)
    if len(data) > MAX_IMAGE_UPLOAD_BYTES:
        raise ValueError("Book images must be 5 MB or smaller.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in ("JPEG", "PNG"):
                    raise ValueError("Please upload a JPG or PNG image.")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("The image dimensions are too large.")
                image.load()
                image_format = image.format
                if image_format == "JPEG":
                    image = image.convert("RGB")
                elif image.mode not in ("1", "L", "LA", "P", "RGB", "RGBA"):
                    image = image.convert("RGBA")
                output = BytesIO()
                image.save(output, format=image_format, optimize=True)
                return image_format.lower(), output.getvalue()
    except ValueError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning,
            UnidentifiedImageError, OSError) as exc:
        raise ValueError("The uploaded file is not a valid JPG or PNG image.") from exc

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    subject = request.args.get("subject", "").strip()
    semester = request.args.get("semester", "").strip()
    book_type = request.args.get("type", "").strip()
    sql = """SELECT books.*, users.name AS owner_name FROM books
             JOIN users ON users.id=books.owner_id
             WHERE books.status='Available'"""
    params = []
    if q:
        sql += " AND (books.title LIKE ? OR books.author LIKE ? OR books.subject LIKE ?)"
        params += [f"%{q}%"] * 3
    if subject:
        sql += " AND books.subject=?"
        params.append(subject)
    if semester:
        sql += " AND books.semester=?"
        params.append(semester)
    if book_type in ("Exchange", "Donation"):
        sql += " AND books.book_type=?"
        params.append(book_type)
    sql += " ORDER BY books.created_at DESC"
    with get_db() as db:
        books = db.execute(sql, params).fetchall()
        subjects = db.execute("SELECT DISTINCT subject FROM books ORDER BY subject").fetchall()
        semesters = db.execute("SELECT DISTINCT semester FROM books ORDER BY semester").fetchall()
    return render_template("index.html", books=books, subjects=subjects, semesters=semesters,
                           q=q, selected_subject=subject, selected_semester=semester, selected_type=book_type)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 6:
            flash("Enter all details. Password must contain at least 6 characters.", "danger")
            return render_template("register.html")
        try:
            with get_db() as db:
                db.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",
                           (name, email, generate_password_hash(password)))
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("An account with that email already exists.", "danger")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            flash(f"Welcome, {user['name']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/books/add", methods=["GET", "POST"])
@login_required
def add_book():
    if request.method == "POST":
        fields = ["title", "author", "subject", "semester", "condition", "book_type"]
        values = [request.form.get(field, "").strip() for field in fields]
        description = request.form.get("description", "").strip()
        if not all(values):
            flash("Please complete all required fields.", "danger")
            return render_template("add_book.html")
        try:
            prepared_image = prepare_book_image(request.files.get("book_image"))
        except RequestEntityTooLarge:
            flash("Book images must be 5 MB or smaller.", "danger")
            return render_template("add_book.html")
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("add_book.html")

        image_filename = None
        if prepared_image:
            image_format, image_data = prepared_image
            image_filename = f"{uuid4().hex}.{image_format}"
            UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
            (UPLOAD_FOLDER / image_filename).write_bytes(image_data)
        with get_db() as db:
            try:
                db.execute("""INSERT INTO books(owner_id,title,author,subject,semester,condition,book_type,description,image_filename)
                              VALUES(?,?,?,?,?,?,?,?,?)""",
                           (session["user_id"], *values, description, image_filename))
            except sqlite3.Error:
                if image_filename:
                    (UPLOAD_FOLDER / image_filename).unlink(missing_ok=True)
                raise
        flash("Your book has been listed.", "success")
        return redirect(url_for("dashboard"))
    return render_template("add_book.html")

@app.route("/books/<int:book_id>")
def book_detail(book_id):
    with get_db() as db:
        book = db.execute("""SELECT books.*, users.name AS owner_name FROM books
                             JOIN users ON users.id=books.owner_id WHERE books.id=?""", (book_id,)).fetchone()
    if not book:
        flash("Book not found.", "danger")
        return redirect(url_for("index"))
    return render_template("book_detail.html", book=book)

@app.route("/books/<int:book_id>/request", methods=["POST"])
@login_required
def request_book(book_id):
    message = request.form.get("message", "").strip()
    with get_db() as db:
        db.execute("BEGIN IMMEDIATE")
        book = db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        if not book or book["status"] != "Available":
            flash("This book is no longer available.", "warning")
        elif book["owner_id"] == session["user_id"]:
            flash("You cannot request your own book.", "warning")
        else:
            existing = db.execute("""SELECT id FROM book_requests
                WHERE book_id=? AND requester_id=? AND status IN ('Pending','Accepted')""",
                (book_id, session["user_id"])).fetchone()
            if existing:
                flash("You already have an active request for this book.", "warning")
            else:
                db.execute("INSERT INTO book_requests(book_id,requester_id,message) VALUES(?,?,?)",
                           (book_id, session["user_id"], message))
                flash("Book request sent. You can track it in My Dashboard → My Requests / History.", "success")
    return redirect(url_for("book_detail", book_id=book_id))

@app.route("/requests/<int:request_id>/<action>", methods=["POST"])
@login_required
def update_request(request_id, action):
    """Let the book owner safely update a request's status."""
    if action not in ("accept", "complete", "reject"):
        flash("Invalid action.", "danger")
        return redirect(url_for("dashboard"))

    uid = session["user_id"]
    with get_db() as db:
        # Begin an immediate transaction so two owners/actions cannot reserve the
        # same book at the same time.
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("""SELECT r.*, b.owner_id, b.id AS bid, b.status AS book_status
                            FROM book_requests r
                            JOIN books b ON b.id=r.book_id
                            WHERE r.id=?""", (request_id,)).fetchone()
        if not row:
            flash("Request not found.", "danger")
            return redirect(url_for("dashboard"))
        if row["owner_id"] != uid:
            flash("Only the owner of this book can manage its requests.", "danger")
            return redirect(url_for("dashboard"))

        current = row["status"]
        book_status = row["book_status"]

        if action == "accept":
            if current != "Pending" or book_status != "Available":
                flash("This request cannot be accepted because it is no longer pending or the book is unavailable.", "warning")
                return redirect(url_for("dashboard"))
            # Only one request can be accepted for a book. Other pending requests
            # are retained in history but marked Rejected.
            db.execute("""UPDATE book_requests
                          SET status='Rejected', updated_at=CURRENT_TIMESTAMP
                          WHERE book_id=? AND id<>? AND status='Pending'""", (row["bid"], request_id))
            db.execute("UPDATE book_requests SET status='Accepted', updated_at=CURRENT_TIMESTAMP WHERE id=?", (request_id,))
            db.execute("UPDATE books SET status='Reserved' WHERE id=? AND status='Available'", (row["bid"],))
            flash("Request accepted. The book is now reserved.", "success")

        elif action == "reject":
            if current != "Pending":
                flash("Only pending requests can be rejected.", "warning")
                return redirect(url_for("dashboard"))
            db.execute("UPDATE book_requests SET status='Rejected', updated_at=CURRENT_TIMESTAMP WHERE id=?", (request_id,))
            flash("Request rejected.", "success")

        elif action == "complete":
            if current != "Accepted" or book_status != "Reserved":
                flash("Only an accepted request can be marked completed.", "warning")
                return redirect(url_for("dashboard"))
            db.execute("UPDATE book_requests SET status='Completed', updated_at=CURRENT_TIMESTAMP WHERE id=?", (request_id,))
            db.execute("UPDATE books SET status='Completed' WHERE id=?", (row["bid"],))
            flash("Transaction completed. It is now saved in both students' history.", "success")

    return redirect(url_for("dashboard"))

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    with get_db() as db:
        my_books = db.execute("SELECT * FROM books WHERE owner_id=? ORDER BY created_at DESC", (uid,)).fetchall()
        incoming = db.execute("""SELECT r.*, b.title, b.book_type, u.name AS requester_name,
            CASE WHEN r.status='Accepted' THEN u.email END AS requester_email, b.id AS bid
            FROM book_requests r JOIN books b ON b.id=r.book_id JOIN users u ON u.id=r.requester_id
            WHERE b.owner_id=? ORDER BY r.created_at DESC""", (uid,)).fetchall()
        outgoing = db.execute("""SELECT r.*, b.title, b.book_type, u.name AS owner_name,
            CASE WHEN r.status='Accepted' THEN u.email END AS owner_email
            FROM book_requests r JOIN books b ON b.id=r.book_id JOIN users u ON u.id=b.owner_id
            WHERE r.requester_id=? ORDER BY r.created_at DESC""", (uid,)).fetchall()
        stats = {
            "books": db.execute(
                "SELECT COUNT(*) FROM books WHERE owner_id=?", (uid,)
            ).fetchone()[0],
            # Count requests sent by this student OR received for their books.
            # UNION removes duplicate IDs if a request ever matches both sides.
            "active": db.execute("""SELECT COUNT(*) FROM (
                SELECT r.id FROM book_requests r
                JOIN books b ON b.id=r.book_id
                WHERE r.status IN ('Pending','Accepted')
                  AND (r.requester_id=? OR b.owner_id=?)
                GROUP BY r.id
            )""", (uid, uid)).fetchone()[0],
            "completed": db.execute("""SELECT COUNT(*) FROM book_requests r
                JOIN books b ON b.id=r.book_id
                WHERE (r.requester_id=? OR b.owner_id=?)
                  AND r.status='Completed'""", (uid, uid)).fetchone()[0]
        }
    return render_template("dashboard.html", my_books=my_books, incoming=incoming, outgoing=outgoing, stats=stats)

if __name__ == "__main__":
    app.run(debug=True)
