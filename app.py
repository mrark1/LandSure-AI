from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
import re
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DB_NAME = os.environ.get("DATABASE_PATH", str(BASE_DIR / "landsure.db"))
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
ALLOWED_EXTENSIONS = {"txt", "pdf", "png", "jpg", "jpeg"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "development-only-secret")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            owner TEXT,
            khasra TEXT,
            khata TEXT,
            area TEXT,
            village TEXT,
            tehsil TEXT,
            district TEXT,
            confidence REAL,
            status TEXT,
            validation TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def allowed_file(filename):
    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def extract_fields(text):
    def find(pattern):
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else "Not detected"

    owner = find(r"Owner\s*[:\-]\s*(.+)")
    khasra = find(r"Khasra\s*(?:No)?\s*[:\-]\s*(.+)")
    khata = find(r"Khata\s*(?:No)?\s*[:\-]\s*(.+)")
    area = find(r"Area\s*[:\-]\s*(.+)")
    village = find(r"Village\s*[:\-]\s*(.+)")
    tehsil = find(r"Tehsil\s*[:\-]\s*(.+)")
    district = find(r"District\s*[:\-]\s*(.+)")

    fields = [owner, khasra, khata, area, village, tehsil, district]
    detected = sum(value != "Not detected" for value in fields)
    confidence = round((detected / len(fields)) * 100, 1)
    status = "Ready for Verification" if confidence >= 80 else "Needs Review"
    validation = "Passed" if khasra != "Not detected" and owner != "Not detected" else "Manual Validation Required"

    return {
        "owner": owner,
        "khasra": khasra,
        "khata": khata,
        "area": area,
        "village": village,
        "tehsil": tehsil,
        "district": district,
        "confidence": confidence,
        "status": status,
        "validation": validation,
    }


def dashboard_context(records):
    total = len(records)
    verified = sum(r["status"] == "Verified" for r in records)
    pending = sum(r["status"] != "Verified" for r in records)
    errors = sum(r["validation"] != "Passed" for r in records)
    accuracy = round(sum(r["confidence"] for r in records) / total, 1) if total else 0
    return {
        "records": records,
        "total": total,
        "verified": verified,
        "pending": pending,
        "errors": errors,
        "duplicates": 0,
        "accuracy": accuracy,
    }


@app.errorhandler(413)
def request_entity_too_large(_error):
    flash("File is too large. Maximum upload size is 10 MB.")
    return redirect(url_for("dashboard"))


@app.route("/")
def dashboard():
    conn = get_db()
    records = conn.execute("SELECT * FROM records ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("dashboard.html", **dashboard_context(records))


@app.route("/upload", methods=["POST"])
def upload():
    if "document" not in request.files:
        flash("Please select a document.")
        return redirect(url_for("dashboard"))

    file = request.files["document"]
    if not file.filename:
        flash("No file selected.")
        return redirect(url_for("dashboard"))

    if not allowed_file(file.filename):
        flash("Unsupported file type. Please upload PDF, image, or TXT files.")
        return redirect(url_for("dashboard"))

    original_filename = secure_filename(file.filename)
    if not original_filename:
        flash("Invalid filename.")
        return redirect(url_for("dashboard"))

    extension = Path(original_filename).suffix.lower()
    if extension == ".txt":
        text = file.read().decode("utf-8", errors="ignore")
    else:
        # Demo fallback: replace this with real OCR/document AI in production.
        text = """
        Owner: Rahul Sharma
        Khasra: 245/B
        Khata: 87
        Area: 1.75 Ha
        Village: Rampur
        Tehsil: Sadar
        District: Kanpur Nagar
        """

    # Prefix with a timestamp to avoid collisions between uploads with the same name.
    stored_filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original_filename}"
    filepath = Path(app.config["UPLOAD_FOLDER"]) / stored_filename
    file.seek(0)
    file.save(filepath)

    result = extract_fields(text)
    conn = get_db()
    cursor = conn.execute("""
        INSERT INTO records
        (filename, owner, khasra, khata, area, village, tehsil, district,
         confidence, status, validation, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        original_filename,
        result["owner"], result["khasra"], result["khata"], result["area"],
        result["village"], result["tehsil"], result["district"],
        result["confidence"], result["status"], result["validation"],
        datetime.now().strftime("%d-%m-%Y %H:%M"),
    ))
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()

    return redirect(url_for("record", record_id=record_id))


@app.route("/record/<int:record_id>")
def record(record_id):
    conn = get_db()
    record_data = conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
    conn.close()

    if not record_data:
        return "Record not found", 404

    return render_template("record.html", record=record_data)


@app.route("/verify/<int:record_id>", methods=["POST"])
def verify(record_id):
    conn = get_db()
    cursor = conn.execute(
        "UPDATE records SET status='Verified', validation='Passed' WHERE id=?",
        (record_id,),
    )
    conn.commit()
    conn.close()

    if cursor.rowcount == 0:
        return "Record not found", 404

    flash("Land record successfully verified.")
    return redirect(url_for("record", record_id=record_id))


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    conn = get_db()
    records = conn.execute("""
        SELECT * FROM records
        WHERE owner LIKE ? OR khasra LIKE ? OR village LIKE ? OR district LIKE ?
        ORDER BY id DESC
    """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%")).fetchall()
    conn.close()
    return render_template("dashboard.html", **dashboard_context(records))


# Initialize the database when the application is imported by Gunicorn.
init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
