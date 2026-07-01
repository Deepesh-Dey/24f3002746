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


def getTrekById(trekId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("SELECT * FROM treks WHERE id = ? LIMIT 1", (trekId,))
	trek = cursor.fetchone()
	connection.close()
	return trek


def getCurrentUser():
	userId = session.get("userId")
	if userId is None:
		return None
	return getUserById(userId)


def buildSearchPattern(value):
	value = (value or "").strip()
	if not value:
		return None
	return f"%{value}%"


def fetchStats():
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("SELECT COUNT(*) FROM treks")
	trekCount = cursor.fetchone()[0]
	cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'trekker'")
	userCount = cursor.fetchone()[0]
	cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'staff'")
	staffCount = cursor.fetchone()[0]
	cursor.execute("SELECT COUNT(*) FROM bookings")
	bookingCount = cursor.fetchone()[0]
	connection.close()
	return {
		"trekCount": trekCount,
		"userCount": userCount,
		"staffCount": staffCount,
		"bookingCount": bookingCount,
	}


def fetchTreks(searchText=None):
	connection = getConnection()
	cursor = connection.cursor()
	pattern = buildSearchPattern(searchText)

	if pattern is None:
		cursor.execute(
			"""
			SELECT t.*, u.name AS staff_name
			FROM treks t
			LEFT JOIN users u ON u.id = t.assigned_staff_id
			ORDER BY t.id DESC
			"""
		)
	else:
		cursor.execute(
			"""
			SELECT t.*, u.name AS staff_name
			FROM treks t
			LEFT JOIN users u ON u.id = t.assigned_staff_id
			WHERE t.trek_name LIKE ? OR t.location LIKE ? OR CAST(t.id AS TEXT) LIKE ?
			ORDER BY t.id DESC
			""",
			(pattern, pattern, pattern),
		)

	treks = cursor.fetchall()
	connection.close()
	return treks


def fetchUsers(searchText=None):
	connection = getConnection()
	cursor = connection.cursor()
	pattern = buildSearchPattern(searchText)

	if pattern is None:
		cursor.execute("SELECT * FROM users ORDER BY id DESC")
	else:
		cursor.execute(
			"""
			SELECT * FROM users
			WHERE name LIKE ? OR email LIKE ? OR CAST(id AS TEXT) LIKE ?
			ORDER BY id DESC
			""",
			(pattern, pattern, pattern),
		)

	users = cursor.fetchall()
	connection.close()
	return users


def fetchStaff(searchText=None):
	connection = getConnection()
	cursor = connection.cursor()
	pattern = buildSearchPattern(searchText)

	baseQuery = """
		SELECT u.id, u.name, u.email, u.status, sp.approval_status, sp.contact, t.trek_name AS assigned_trek_name
		FROM users u
		LEFT JOIN staff_profile sp ON sp.user_id = u.id
		LEFT JOIN treks t ON t.id = sp.assigned_trek_id
		WHERE u.role = 'staff'
	"""
	if pattern is None:
		cursor.execute(baseQuery + " ORDER BY u.id DESC")
	else:
		cursor.execute(
			baseQuery + " AND (u.name LIKE ? OR u.email LIKE ? OR CAST(u.id AS TEXT) LIKE ?) ORDER BY u.id DESC",
			(pattern, pattern, pattern),
		)

	staff = cursor.fetchall()
	connection.close()
	return staff


def fetchBookings():
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute(
		"""
		SELECT b.*, u.name AS user_name, t.trek_name AS trek_name
		FROM bookings b
		LEFT JOIN users u ON u.id = b.user_id
		LEFT JOIN treks t ON t.id = b.trek_id
		ORDER BY b.id DESC
		"""
	)
	bookings = cursor.fetchall()
	connection.close()
	return bookings


def fetchAssignedTreks(staffId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute(
		"""
		SELECT t.*, COUNT(b.id) AS participant_count
		FROM treks t
		LEFT JOIN bookings b ON b.trek_id = t.id AND b.booking_status != 'Cancelled'
		WHERE t.assigned_staff_id = ?
		GROUP BY t.id
		ORDER BY t.id DESC
		""",
		(staffId,),
	)
	treks = cursor.fetchall()
	connection.close()
	return treks


def fetchTrekParticipants(trekId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute(
		"""
		SELECT b.id AS booking_id, b.booking_status, b.booking_date, b.completed_date, u.name, u.email
		FROM bookings b
		LEFT JOIN users u ON u.id = b.user_id
		WHERE b.trek_id = ?
		ORDER BY b.id DESC
		""",
		(trekId,),
	)
	participants = cursor.fetchall()
	connection.close()
	return participants


def updateStaffProfile(userId, formData):
	contact = formData.get("contact", "").strip()
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("UPDATE staff_profile SET contact = ? WHERE user_id = ?", (contact, userId))
	connection.commit()
	connection.close()


def getStaffOwnedTrek(trekId, staffId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("SELECT * FROM treks WHERE id = ? AND assigned_staff_id = ? LIMIT 1", (trekId, staffId))
	trek = cursor.fetchone()
	connection.close()
	return trek


def updateStaffTrek(trekId, staffId, formData):
	trek = getStaffOwnedTrek(trekId, staffId)
	if trek is None:
		return False

	availableSlots = formData.get("available_slots", str(trek["available_slots"])).strip() or str(trek["available_slots"])
	status = formData.get("status", trek["status"]).strip() or trek["status"]
	startDate = formData.get("start_date", trek["start_date"] or "").strip()
	endDate = formData.get("end_date", trek["end_date"] or "").strip()
	description = formData.get("description", trek["description"] or "").strip()
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute(
		"""
		UPDATE treks
		SET available_slots = ?, status = ?, start_date = ?, end_date = ?, description = ?
		WHERE id = ? AND assigned_staff_id = ?
		""",
		(int(availableSlots), status, startDate, endDate, description, trekId, staffId),
	)
	connection.commit()
	connection.close()

	# once staff marks the trek completed, close out the bookings too
	if status == "Completed":
		completeTrekBookings(trekId)

	return True


def completeTrekBookings(trekId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute(
		"""
		UPDATE bookings
		SET booking_status = 'Completed', completed_date = CURRENT_TIMESTAMP
		WHERE trek_id = ? AND booking_status = 'Booked'
		""",
		(trekId,),
	)
	connection.commit()
	connection.close()


def fetchOpenTreks(difficulty=None, location=None):
	connection = getConnection()
	cursor = connection.cursor()
	difficultyPattern = buildSearchPattern(difficulty)
	locationPattern = buildSearchPattern(location)

	query = "SELECT * FROM treks WHERE status = 'Open' AND available_slots > 0"
	params = []

	if difficultyPattern:
		query += " AND difficulty LIKE ?"
		params.append(difficultyPattern)

	if locationPattern:
		query += " AND location LIKE ?"
		params.append(locationPattern)

	query += " ORDER BY id DESC"
	cursor.execute(query, params)
	treks = cursor.fetchall()
	connection.close()
	return treks


def fetchUserBookings(userId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute(
		"""
		SELECT b.*, t.trek_name, t.location, t.difficulty, t.status AS trek_status
		FROM bookings b
		LEFT JOIN treks t ON t.id = b.trek_id
		WHERE b.user_id = ?
		ORDER BY b.id DESC
		""",
		(userId,),
	)
	bookings = cursor.fetchall()
	connection.close()
	return bookings


def hasActiveBooking(userId, trekId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute(
		"SELECT id FROM bookings WHERE user_id = ? AND trek_id = ? AND booking_status = 'Booked' LIMIT 1",
		(userId, trekId),
	)
	row = cursor.fetchone()
	connection.close()
	return row is not None


def bookTrek(userId, trekId):
	trek = getTrekById(trekId)

	# guard against closed treks, full treks and duplicate bookings
	if trek is None:
		return "trek not found"
	if trek["status"] != "Open":
		return "trek is not open for booking"
	if trek["available_slots"] <= 0:
		return "no slots available for this trek"
	if hasActiveBooking(userId, trekId):
		return "you already booked this trek"

	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute(
		"INSERT INTO bookings (user_id, trek_id, booking_status, payment_status) VALUES (?, ?, ?, ?)",
		(userId, trekId, "Booked", "Pending"),
	)
	cursor.execute("UPDATE treks SET available_slots = available_slots - 1 WHERE id = ?", (trekId,))
	connection.commit()
	connection.close()
	return None


def cancelBooking(bookingId, userId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("SELECT * FROM bookings WHERE id = ? AND user_id = ? LIMIT 1", (bookingId, userId))
	booking = cursor.fetchone()

	if booking is None or booking["booking_status"] != "Booked":
		connection.close()
		return False

	cursor.execute("UPDATE bookings SET booking_status = 'Cancelled' WHERE id = ?", (bookingId,))
	cursor.execute("UPDATE treks SET available_slots = available_slots + 1 WHERE id = ?", (booking["trek_id"],))
	connection.commit()
	connection.close()
	return True


def updateUserProfile(userId, formData):
	name = formData.get("name", "").strip()
	newPassword = formData.get("new_password", "").strip()

	connection = getConnection()
	cursor = connection.cursor()

	if name:
		cursor.execute("UPDATE users SET name = ? WHERE id = ?", (name, userId))

	# only touch the password if the user actually typed a new one
	if newPassword:
		cursor.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(newPassword), userId))

	connection.commit()
	connection.close()


def saveTrek(formData, trekId=None):
	trekName = formData.get("trek_name", "").strip()
	difficulty = formData.get("difficulty", "").strip()
	duration = formData.get("duration", "0").strip() or "0"
	availableSlots = formData.get("available_slots", "0").strip() or "0"
	location = formData.get("location", "").strip()
	status = formData.get("status", "Pending").strip() or "Pending"
	startDate = formData.get("start_date", "").strip()
	endDate = formData.get("end_date", "").strip()
	description = formData.get("description", "").strip()
	staffId = formData.get("assigned_staff_id", "").strip() or None

	connection = getConnection()
	cursor = connection.cursor()

	if trekId is None:
		cursor.execute(
			"""
			INSERT INTO treks (
				trek_name, difficulty, duration, available_slots, assigned_staff_id,
				status, start_date, end_date, location, description
			)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			""",
			(
				trekName,
				difficulty,
				int(duration),
				int(availableSlots),
				staffId,
				status,
				startDate,
				endDate,
				location,
				description,
			),
		)
	else:
		cursor.execute(
			"""
			UPDATE treks
			SET trek_name = ?, difficulty = ?, duration = ?, available_slots = ?, assigned_staff_id = ?,
				status = ?, start_date = ?, end_date = ?, location = ?, description = ?
			WHERE id = ?
			""",
			(
				trekName,
				difficulty,
				int(duration),
				int(availableSlots),
				staffId,
				status,
				startDate,
				endDate,
				location,
				description,
				trekId,
			),
		)

	connection.commit()
	connection.close()

	# admin can also close out a trek directly, so complete its bookings too
	if trekId is not None and status == "Completed":
		completeTrekBookings(trekId)


def setUserStatus(userId, status):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("UPDATE users SET status = ? WHERE id = ?", (status, userId))
	connection.commit()
	connection.close()


def setStaffApproval(userId, approvalStatus):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("UPDATE staff_profile SET approval_status = ? WHERE user_id = ?", (approvalStatus, userId))
	connection.commit()
	connection.close()


def setTrekStaff(trekId, staffId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("UPDATE treks SET assigned_staff_id = ? WHERE id = ?", (staffId or None, trekId))
	connection.commit()
	connection.close()


def loginRequired(viewFunc):
	@wraps(viewFunc)
	def wrapper(*args, **kwargs):
		user = getCurrentUser()
		if user is None or user["status"] != "active":
			session.clear()
			return redirect(url_for("login"))
		return viewFunc(*args, **kwargs)

	return wrapper


def roleRequired(*roles):
	def decorator(viewFunc):
		@wraps(viewFunc)
		def wrapper(*args, **kwargs):
			user = getCurrentUser()
			if user is None or user["status"] != "active":
				session.clear()
				return redirect(url_for("login"))

			if user["role"] not in roles:
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

		if user["status"] != "active":
			flash("account is not active")
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
	stats = fetchStats()
	treks = fetchTreks(request.args.get("trekSearch"))
	users = fetchUsers(request.args.get("userSearch"))
	staff = fetchStaff(request.args.get("staffSearch"))
	bookings = fetchBookings()
	return render_template(
		"admin_dashboard.html",
		stats=stats,
		treks=treks,
		users=users,
		staff=staff,
		bookings=bookings,
		currentUser=getCurrentUser(),
	)


@app.route("/admin/treks/add", methods=["POST"])
@loginRequired
@roleRequired("admin")
def addTrek():
	saveTrek(request.form)
	flash("trek saved")
	return redirect(url_for("adminDashboard"))


@app.route("/admin/treks/<int:trekId>/edit", methods=["POST"])
@loginRequired
@roleRequired("admin")
def editTrek(trekId):
	saveTrek(request.form, trekId)
	flash("trek updated")
	return redirect(url_for("adminDashboard"))


@app.route("/admin/treks/<int:trekId>/delete", methods=["POST"])
@loginRequired
@roleRequired("admin")
def deleteTrek(trekId):
	connection = getConnection()
	cursor = connection.cursor()
	cursor.execute("DELETE FROM treks WHERE id = ?", (trekId,))
	connection.commit()
	connection.close()
	flash("trek removed")
	return redirect(url_for("adminDashboard"))


@app.route("/admin/treks/<int:trekId>/assign", methods=["POST"])
@loginRequired
@roleRequired("admin")
def assignTrekStaff(trekId):
	staffId = request.form.get("assigned_staff_id", "").strip() or None
	setTrekStaff(trekId, staffId)
	flash("staff assigned")
	return redirect(url_for("adminDashboard"))


@app.route("/admin/users/<int:userId>/toggle", methods=["POST"])
@loginRequired
@roleRequired("admin")
def toggleUserStatus(userId):
	user = getUserById(userId)
	if user is None:
		flash("user not found")
		return redirect(url_for("adminDashboard"))

	if user["role"] == "admin":
		flash("admin cannot be changed")
		return redirect(url_for("adminDashboard"))

	newStatus = "active" if user["status"] != "active" else "blacklisted"
	setUserStatus(userId, newStatus)
	if user["role"] == "staff":
		setStaffApproval(userId, "approved" if newStatus == "active" else "blacklisted")
	flash("user status updated")
	return redirect(url_for("adminDashboard"))


@app.route("/admin/staff/<int:userId>/approve", methods=["POST"])
@loginRequired
@roleRequired("admin")
def approveStaff(userId):
	setStaffApproval(userId, "approved")
	flash("staff approved")
	return redirect(url_for("adminDashboard"))


@app.route("/admin/staff/<int:userId>/blacklist", methods=["POST"])
@loginRequired
@roleRequired("admin")
def blacklistStaff(userId):
	setUserStatus(userId, "blacklisted")
	setStaffApproval(userId, "blacklisted")
	flash("staff blacklisted")
	return redirect(url_for("adminDashboard"))


@app.route("/staff")
@loginRequired
@roleRequired("staff")
def staffDashboard():
	currentUser = getCurrentUser()
	profile = getStaffProfile(currentUser["id"])
	treks = fetchAssignedTreks(currentUser["id"])
	selectedTrekId = request.args.get("trekId")
	selectedTrek = None
	participants = []
	if selectedTrekId:
		selectedTrek = getStaffOwnedTrek(int(selectedTrekId), currentUser["id"])
		if selectedTrek is not None:
			participants = fetchTrekParticipants(selectedTrek["id"])

	return render_template(
		"staff_dashboard.html",
		currentUser=currentUser,
		profile=profile,
		treks=treks,
		selectedTrek=selectedTrek,
		participants=participants,
	)


@app.route("/staff/profile/update", methods=["POST"])
@loginRequired
@roleRequired("staff")
def updateStaffProfileRoute():
	currentUser = getCurrentUser()
	updateStaffProfile(currentUser["id"], request.form)
	flash("profile updated")
	return redirect(url_for("staffDashboard"))


@app.route("/staff/treks/<int:trekId>/update", methods=["POST"])
@loginRequired
@roleRequired("staff")
def updateStaffTrekRoute(trekId):
	currentUser = getCurrentUser()
	if not updateStaffTrek(trekId, currentUser["id"], request.form):
		flash("only assigned staff can manage this trek")
		return redirect(url_for("staffDashboard"))

	flash("trek updated")
	return redirect(url_for("staffDashboard", trekId=trekId))


@app.route("/staff/treks/<int:trekId>")
@loginRequired
@roleRequired("staff")
def viewStaffTrek(trekId):
	currentUser = getCurrentUser()
	trek = getStaffOwnedTrek(trekId, currentUser["id"])
	if trek is None:
		flash("only assigned staff can manage this trek")
		return redirect(url_for("staffDashboard"))

	participants = fetchTrekParticipants(trekId)
	return render_template(
		"staff_dashboard.html",
		currentUser=currentUser,
		profile=getStaffProfile(currentUser["id"]),
		treks=fetchAssignedTreks(currentUser["id"]),
		selectedTrek=trek,
		participants=participants,
	)


@app.route("/user")
@loginRequired
@roleRequired("trekker")
def userDashboard():
	currentUser = getCurrentUser()
	difficulty = request.args.get("difficulty", "")
	location = request.args.get("location", "")
	openTreks = fetchOpenTreks(difficulty, location)
	myBookings = fetchUserBookings(currentUser["id"])

	# used by the template to hide the book button for treks already booked
	activeTrekIds = [booking["trek_id"] for booking in myBookings if booking["booking_status"] == "Booked"]

	return render_template(
		"user_dashboard.html",
		currentUser=currentUser,
		openTreks=openTreks,
		myBookings=myBookings,
		activeTrekIds=activeTrekIds,
		difficulty=difficulty,
		location=location,
	)


@app.route("/user/profile/update", methods=["POST"])
@loginRequired
@roleRequired("trekker")
def updateUserProfileRoute():
	currentUser = getCurrentUser()
	updateUserProfile(currentUser["id"], request.form)
	flash("profile updated")
	return redirect(url_for("userDashboard"))


@app.route("/user/treks/<int:trekId>/book", methods=["POST"])
@loginRequired
@roleRequired("trekker")
def bookTrekRoute(trekId):
	currentUser = getCurrentUser()
	error = bookTrek(currentUser["id"], trekId)
	if error:
		flash(error)
	else:
		flash("trek booked")
	return redirect(url_for("userDashboard"))


@app.route("/user/bookings/<int:bookingId>/cancel", methods=["POST"])
@loginRequired
@roleRequired("trekker")
def cancelBookingRoute(bookingId):
	currentUser = getCurrentUser()
	if cancelBooking(bookingId, currentUser["id"]):
		flash("booking cancelled")
	else:
		flash("booking not found or already cancelled")
	return redirect(url_for("userDashboard"))


if __name__ == "__main__":
	initDatabase()
	seedAdmin()
	app.run(debug=True)
