# AdventureHub
Trekking Management Application - Modern Application Development I (IITM BS DS Course Project)

## Tech Stack
- Python 3.9+ (developed and tested on Python 3.13)
- Flask 3.1.3 (backend, routing)
- Flask-Login 0.6.3 (session and login handling)
- Werkzeug 3.1.8 (password hashing, installed alongside Flask)
- Jinja2 (frontend templates, installed alongside Flask)
- Bootstrap 5.3.3 (styling, loaded from a CDN `<link>` tag in each template - no local install needed, but the browser needs internet access to load it)
- SQLite (database, created automatically on first run, built into Python's standard library)

## What You Need Installed
- Python 3.9 or newer
- pip (comes with Python)
- Everything else (Flask, Flask-Login, Werkzeug) comes from `requirements.txt` below - no other installs required.

## How to Run
1. Make sure Python 3.9 or newer is installed.
2. (Recommended) create and activate a virtual environment:
   - Windows: `python -m venv venv` then `venv\Scripts\activate`
   - Mac/Linux: `python -m venv venv` then `source venv/bin/activate`
3. Install the dependencies:
   `pip install -r requirements.txt`
4. Run the app:
   `python app.py`
5. Open `http://127.0.0.1:5000` in your browser (needs an internet connection so the Bootstrap CSS CDN link can load - the app itself runs fully offline otherwise).

The database file `adventurehub.db` is created automatically the first time the app runs (it is not part of the submitted code, it gets generated fresh), along with a default admin account.

## Default Admin Login
- Email: `admin@adventurehub.local`
- Password: `admin123`

## Roles
- **Admin**: manages treks, approves/blacklists staff and users, views all bookings and history.
- **Trek Staff**: registers and needs admin approval before login works, manages only their assigned treks and participants.
- **Trekker (User)**: registers, browses/filters open treks, books and cancels treks, views their own booking history.

## Project Structure
- `app.py` - all routes, database setup and business logic
- `templates/` - Jinja2 HTML templates (Bootstrap 5 based)
- `requirements.txt` - Python dependencies
- `openapi.yaml` - API definition for the JSON endpoints under `/api/...`

## API
A JSON API is available under `/api/...` (full definition in `openapi.yaml`). It uses the same login session as the website - log in through `/login` first, then call the API endpoints with that same session/cookie.