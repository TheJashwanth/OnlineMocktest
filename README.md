# Online Mock Test Platform (Mini Project)

A complete Flask-based mock test platform with:
- Instructor exam creation from a question paper text format.
- Auto-generated exam code to share with students.
- Student login restricted to a college domain email.
- Timed exam with auto-submit.
- Result calculation and storage.

## Features

1. **Instructor flow**
   - Login with instructor key.
   - Paste question paper in a simple format.
   - System generates an exam code.

2. **Student flow**
   - Login using `@college.edu` (or configured domain).
   - Enter exam code.
   - Write exam with visible countdown timer.
   - Submit and view score.

## Question Paper Format

```text
Q: What is 2 + 2?
- 3
- 4
- 5
A: 4

Q: Capital of France?
- London
- Paris
- Rome
A: Paris
```

Rules:
- Start each question with `Q:`
- Options start with `-`
- Correct option starts with `A:` and must exactly match one option

## Setup & Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open: `http://localhost:5000`

## Environment Variables

- `SECRET_KEY` - Flask session secret.
- `DATABASE_PATH` - SQLite DB path (default `exam.db`).
- `COLLEGE_DOMAIN` - allowed student email domain (default `college.edu`).
- `ADMIN_KEY` - instructor login key (default `admin123`).

Example:

```bash
export COLLEGE_DOMAIN=mycollege.edu
export ADMIN_KEY=supersecure
python app.py
```

## Notes

- This is a mini-project starter and can be extended with OTP/email verification, proctoring, question randomization, negative marking, and admin analytics.
