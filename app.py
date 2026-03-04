import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["DATABASE"] = os.environ.get("DATABASE_PATH", "exam.db")
app.config["COLLEGE_DOMAIN"] = os.environ.get("COLLEGE_DOMAIN", "college.edu")
app.config["ADMIN_KEY"] = os.environ.get("ADMIN_KEY", "admin123")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            exam_code TEXT UNIQUE NOT NULL,
            duration_minutes INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            questions_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            student_email TEXT NOT NULL,
            started_at TEXT NOT NULL,
            submitted_at TEXT,
            answers_json TEXT,
            score INTEGER,
            total INTEGER,
            FOREIGN KEY(exam_id) REFERENCES exams(id),
            UNIQUE(exam_id, student_email)
        );
        """
    )
    db.commit()


@app.before_request
def ensure_db():
    init_db()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "student_email" not in session:
            flash("Please sign in with your college email.")
            return redirect(url_for("student_login"))
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            flash("Instructor access required.")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)

    return wrapper


def parse_questions(raw_text):
    questions = []
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    current = None
    for line in lines:
        if line.startswith("Q:"):
            if current:
                questions.append(current)
            current = {"question": line[2:].strip(), "options": [], "answer": None}
        elif line.startswith("-") and current:
            current["options"].append(line[1:].strip())
        elif line.startswith("A:") and current:
            answer = line[2:].strip()
            current["answer"] = answer
    if current:
        questions.append(current)

    valid = [
        q
        for q in questions
        if q["question"] and len(q["options"]) >= 2 and q["answer"] in q["options"]
    ]
    return valid


def now_iso():
    return datetime.now(timezone.utc).isoformat()


@app.route("/")
def index():
    return render_template("index.html", domain=app.config["COLLEGE_DOMAIN"])


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("admin_key") == app.config["ADMIN_KEY"]:
            session["admin"] = True
            flash("Instructor login successful.")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid instructor key.")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    flash("Logged out.")
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        duration = int(request.form.get("duration_minutes", "30"))
        raw_questions = request.form.get("questions", "")
        questions = parse_questions(raw_questions)

        if not title or not questions:
            flash("Enter title and valid question format.")
            return redirect(url_for("admin_dashboard"))

        exam_code = secrets.token_hex(3).upper()
        db.execute(
            """
            INSERT INTO exams(title, exam_code, duration_minutes, created_at, questions_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, exam_code, duration, now_iso(), json.dumps(questions)),
        )
        db.commit()
        flash(f"Exam created. Share this code: {exam_code}")
        return redirect(url_for("admin_dashboard"))

    exams = db.execute("SELECT * FROM exams ORDER BY id DESC").fetchall()
    return render_template("admin_dashboard.html", exams=exams)


@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        domain = app.config["COLLEGE_DOMAIN"].lower()
        if email.endswith(f"@{domain}"):
            session["student_email"] = email
            flash("Signed in successfully.")
            return redirect(url_for("student_home"))
        flash(f"Use your official @{domain} mail ID.")
    return render_template("student_login.html", domain=app.config["COLLEGE_DOMAIN"])


@app.route("/student/logout")
def student_logout():
    session.pop("student_email", None)
    flash("Logged out.")
    return redirect(url_for("index"))


@app.route("/student", methods=["GET", "POST"])
@login_required
def student_home():
    if request.method == "POST":
        code = request.form.get("exam_code", "").strip().upper()
        return redirect(url_for("start_exam", code=code))
    return render_template("student_home.html", email=session["student_email"])


@app.route("/exam/<code>", methods=["GET", "POST"])
@login_required
def start_exam(code):
    db = get_db()
    exam = db.execute("SELECT * FROM exams WHERE exam_code = ?", (code,)).fetchone()
    if not exam:
        flash("Invalid exam code.")
        return redirect(url_for("student_home"))

    questions = json.loads(exam["questions_json"])
    student_email = session["student_email"]
    attempt = db.execute(
        "SELECT * FROM attempts WHERE exam_id = ? AND student_email = ?",
        (exam["id"], student_email),
    ).fetchone()

    if attempt and attempt["submitted_at"]:
        flash("You already submitted this exam.")
        return redirect(url_for("view_result", attempt_id=attempt["id"]))

    if not attempt:
        db.execute(
            "INSERT INTO attempts(exam_id, student_email, started_at) VALUES (?, ?, ?)",
            (exam["id"], student_email, now_iso()),
        )
        db.commit()
        attempt = db.execute(
            "SELECT * FROM attempts WHERE exam_id = ? AND student_email = ?",
            (exam["id"], student_email),
        ).fetchone()

    started_at = datetime.fromisoformat(attempt["started_at"])
    end_time = started_at + timedelta(minutes=exam["duration_minutes"])

    if request.method == "POST":
        if datetime.now(timezone.utc) > end_time:
            flash("Time over. Auto-submitting with current answers.")

        answers = {}
        score = 0
        for idx, q in enumerate(questions):
            key = f"q{idx}"
            chosen = request.form.get(key, "")
            answers[key] = chosen
            if chosen == q["answer"]:
                score += 1

        db.execute(
            """
            UPDATE attempts
            SET submitted_at = ?, answers_json = ?, score = ?, total = ?
            WHERE id = ?
            """,
            (now_iso(), json.dumps(answers), score, len(questions), attempt["id"]),
        )
        db.commit()
        return redirect(url_for("view_result", attempt_id=attempt["id"]))

    remaining = int((end_time - datetime.now(timezone.utc)).total_seconds())
    if remaining <= 0:
        flash("Exam time has already ended for this attempt.")
        return redirect(url_for("student_home"))

    return render_template(
        "exam.html",
        exam=exam,
        questions=questions,
        remaining=remaining,
    )


@app.route("/result/<int:attempt_id>")
@login_required
def view_result(attempt_id):
    db = get_db()
    attempt = db.execute(
        """
        SELECT a.*, e.title, e.exam_code FROM attempts a
        JOIN exams e ON e.id = a.exam_id
        WHERE a.id = ? AND a.student_email = ?
        """,
        (attempt_id, session["student_email"]),
    ).fetchone()
    if not attempt:
        flash("Result not found.")
        return redirect(url_for("student_home"))
    return render_template("result.html", attempt=attempt)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
