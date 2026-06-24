import sqlite3
from pathlib import Path
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "adventurehub.db"

app = Flask(__name__)
app.secret_key = "adventurehub-secret"


def getConnection():
	connection = sqlite3.connect(DB_PATH)
	connection.row_factory = sqlite3.Row
	return connection


def createTables(cursor):
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS users (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			name TEXT NOT NULL,
			email TEXT NOT NULL UNIQUE,
			password TEXT NOT NULL,
			role TEXT NOT NULL CHECK(role IN ('admin', 'staff', 'trekker')),
			status TEXT NOT NULL DEFAULT 'active',
			created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
		)
	""")

	cursor.execute("""
		CREATE TABLE IF NOT EXISTS staff_profile (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER NOT NULL UNIQUE,
			contact TEXT,
			assigned_trek_id INTEGER,
			approval_status TEXT NOT NULL DEFAULT 'pending',
			created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (user_id) REFERENCES users (id),
			FOREIGN KEY (assigned_trek_id) REFERENCES treks (id)
		)
	""")

	cursor.execute("""
		CREATE TABLE IF NOT EXISTS treks (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			trek_name TEXT NOT NULL,
			difficulty TEXT NOT NULL,
			duration INTEGER NOT NULL,
			available_slots INTEGER NOT NULL DEFAULT 0,
			assigned_staff_id INTEGER,
			status TEXT NOT NULL DEFAULT 'Pending',
			start_date TEXT,
			end_date TEXT,
			location TEXT,
			description TEXT,
			created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
			FOREIGN KEY (assigned_staff_id) REFERENCES users (id)
		)
	""")

	cursor.execute("""
		CREATE TABLE IF NOT EXISTS bookings (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			user_id INTEGER NOT NULL,
			trek_id INTEGER NOT NULL,
			booking_status TEXT NOT NULL DEFAULT 'Booked',
			booking_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
			payment_status TEXT NOT NULL DEFAULT 'Pending',
			completed_date TEXT,
			FOREIGN KEY (user_id) REFERENCES users (id),
			FOREIGN KEY (trek_id) REFERENCES treks (id)
		)
	""")


def getUserByEmail(email):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("SELECT * FROM users WHERE email = ? LIMIT 1", (email,))
	user = cursor.fetchone()
	connection.close()
	return user


def getUserById(userId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("SELECT * FROM users WHERE id = ? LIMIT 1", (userId,))
	user = cursor.fetchone()
	connection.close()
	return user


def getStaffProfile(userId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("SELECT * FROM staff_profile WHERE user_id = ? LIMIT 1", (userId,))
	profile = cursor.fetchone()
	connection.close()
	return profile


def loginRequired(viewFunc):
	@wraps(viewFunc)
	def wrapper(*args, **kwargs):
		if "userId" not in session:
			return redirect(url_for("login"))
		return viewFunc(*args, **kwargs)

	return wrapper


def roleRequired(*roles):
	def decorator(viewFunc):
		@wraps(viewFunc)
		def wrapper(*args, **kwargs):
			userId = session.get("userId")
			if userId is None:
				return redirect(url_for("login"))

			user = getUserById(userId)
			if user is None or user["role"] not in roles:
				return redirect(url_for("home"))

			return viewFunc(*args, **kwargs)

		return wrapper

	return decorator


def initDatabase():
	connection = getConnection()
	cursor = connection.cursor()

	# make sure the schema exists before anything else
	createTables(cursor)

	connection.commit()
	connection.close()


def seedAdmin():
	connection = getConnection()
	cursor = connection.cursor()

	cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
	adminRow = cursor.fetchone()

	if adminRow is None:
		cursor.execute(
			"""
			INSERT INTO users (name, email, password, role, status)
			VALUES (?, ?, ?, ?, ?)
			""",
			("Admin", "admin@adventurehub.local", generate_password_hash("admin123"), "admin", "active"),
		)

	connection.commit()
	connection.close()


def goToDashboard(userRole):
	if userRole == "admin":
		return redirect(url_for("adminDashboard"))
	if userRole == "staff":
		return redirect(url_for("staffDashboard"))
	return redirect(url_for("userDashboard"))


@app.route("/")
def home():
	if "userId" in session:
		return goToDashboard(session.get("role"))
	return render_template("home.html")


@app.route("/register", methods=["GET", "POST"])
def register():
	if session.get("role") == "admin":
		return redirect(url_for("adminDashboard"))

	if request.method == "POST":
		name = request.form.get("name", "").strip()
		email = request.form.get("email", "").strip().lower()
		password = request.form.get("password", "")
		role = request.form.get("role", "trekker")
		contact = request.form.get("contact", "").strip()

		if not name or not email or not password:
			flash("fill all the fields")
			return render_template("register.html")

		if getUserByEmail(email) is not None:
			flash("email already used")
			return render_template("register.html")

		if role not in ["trekker", "staff"]:
			role = "trekker"

		passwordHash = generate_password_hash(password)
		connection = getConnection()
		cursor = connection.cursor()

		cursor.execute(
			"INSERT INTO users (name, email, password, role, status) VALUES (?, ?, ?, ?, ?)",
			(name, email, passwordHash, role, "active"),
		)
		userId = cursor.lastrowid

		if role == "staff":
			cursor.execute(
				"INSERT INTO staff_profile (user_id, contact, approval_status) VALUES (?, ?, ?)",
				(userId, contact, "pending"),
			)

		connection.commit()
		connection.close()
		flash("registration done")
		return redirect(url_for("login"))

	return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
	if request.method == "POST":
		email = request.form.get("email", "").strip().lower()
		password = request.form.get("password", "")

		user = getUserByEmail(email)
		if user is None or not check_password_hash(user["password"], password):
			flash("wrong login details")
			return render_template("login.html")

		if user["role"] == "staff":
			profile = getStaffProfile(user["id"])
			if profile is None or profile["approval_status"] != "approved":
				flash("staff needs admin approval")
				return render_template("login.html")

		session["userId"] = user["id"]
		session["role"] = user["role"]
		return goToDashboard(user["role"])

	return render_template("login.html")


@app.route("/logout")
def logout():
	session.clear()
	return redirect(url_for("home"))


@app.route("/admin")
@loginRequired
@roleRequired("admin")
def adminDashboard():
	return render_template("admin_dashboard.html")


@app.route("/staff")
@loginRequired
@roleRequired("staff")
def staffDashboard():
	return render_template("staff_dashboard.html")


@app.route("/user")
@loginRequired
@roleRequired("trekker")
def userDashboard():
	return render_template("user_dashboard.html")


if __name__ == "__main__":
	initDatabase()
	seedAdmin()
	app.run(debug=True)
