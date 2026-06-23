import sqlite3
from pathlib import Path

from flask import Flask


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "adventurehub.db"

app = Flask(__name__)


def getConnection():
	# get the local sqlite file
	connection = sqlite3.connect(DB_PATH)
	connection.row_factory = sqlite3.Row
	return connection


def createTables(cursor):
	# keep all tables in one place for now
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

	# add the default admin only once
	cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
	adminRow = cursor.fetchone()

	if adminRow is None:
		cursor.execute(
			"""
			INSERT INTO users (name, email, password, role, status)
			VALUES (?, ?, ?, ?, ?)
			""",
			("Admin", "admin@adventurehub.local", "admin123", "admin", "active"),
		)

	connection.commit()
	connection.close()


@app.route("/")
def home():
	# simple check route for now
	return "AdventureHub database setup is ready."


if __name__ == "__main__":
	initDatabase()
	seedAdmin()
	app.run(debug=True)
