from flask import Flask, render_template, request, session, redirect
import subprocess
import os
import sqlite3

app = Flask(__name__)
app.secret_key = "skillgap_secret_key_123"

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------- HOME ----------------
@app.route("/")
def home():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("index.html", name=session["name"])


# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        conn = sqlite3.connect("skillgap.db")
        cur = conn.cursor()

        try:
            cur.execute(
                "INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                (name,email,password,role)
            )
            conn.commit()
            conn.close()
            return redirect("/login")
        except:
            conn.close()
            return "Email already exists"

    return render_template("register.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("skillgap.db")
        cur = conn.cursor()

        user = cur.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email,password)
        ).fetchone()

        conn.close()

        if user:
            session["user_id"] = user[0]
            session["name"] = user[1]
            session["role"] = user[4]
            return redirect("/")
        else:
            return "Invalid login"

    return render_template("login.html")


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- HISTORY ----------------
@app.route("/history")
def history():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT id, role_target, strong, moderate, missing
        FROM reports
        WHERE user_id=?
        ORDER BY id DESC
    """, (session["user_id"],)).fetchall()

    reports = []

    for r in rows:

        report_id = r[0]

        rating_rows = cur.execute(
            "SELECT skill,rating FROM ratings WHERE report_id=?",
            (report_id,)
        ).fetchall()

        rating_dict = {skill:rating for skill,rating in rating_rows}

        reports.append({
            "role": r[1],
            "strong": r[2].split(",") if r[2] else [],
            "moderate": r[3].split(",") if r[3] else [],
            "missing": r[4].split(",") if r[4] else [],
            "ratings": rating_dict
        })

    conn.close()

    return render_template("history.html", reports=reports)

@app.route("/teacher")
def teacher_dashboard():

    if "user_id" not in session or session["role"] != "teacher":
        return redirect("/")

    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT reports.id, users.name, users.email, reports.role_target,
           reports.strong, reports.moderate, reports.missing
    FROM reports
    JOIN users ON users.id = reports.user_id
    ORDER BY reports.id DESC
    """).fetchall()

    data = []

    for r in rows:

        report_id = r[0]

        # fetch ratings for this report
        rating_rows = cur.execute(
            "SELECT skill,rating FROM ratings WHERE report_id=?",
            (report_id,)
        ).fetchall()

        rating_dict = {skill:rating for skill,rating in rating_rows}

        data.append({
            "report_id": report_id,
            "name": r[1],
            "email": r[2],
            "role": r[3],
            "strong": r[4].split(",") if r[4] else [],
            "moderate": r[5].split(",") if r[5] else [],
            "missing": r[6].split(",") if r[6] else [],
            "ratings": rating_dict
        })

    conn.close()

    return render_template("teacher.html", data=data)

@app.route("/rate", methods=["POST"])
def rate_skill():

    if session.get("role") != "teacher":
        return redirect("/")

    report_id = request.form["report_id"]
    skill = request.form["skill"]
    rating = request.form["rating"]

    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO ratings(report_id,skill,rating) VALUES(?,?,?)",
        (report_id,skill,rating)
    )

    conn.commit()
    conn.close()

    return redirect("/teacher")



@app.route("/full_analysis", methods=["POST"])
def full_analysis():

    if "user_id" not in session:
        return redirect("/login")

    # -------- Save Resume --------
    file = request.files["resume"]
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    # -------- Resume Analysis --------
    resume_raw = subprocess.getoutput(f'python analyze_resume.py "{filepath}"')
    resume_skills = [
        line.strip("- ").strip()
        for line in resume_raw.split("\n")
        if line.startswith("-")
    ]

    # -------- GitHub Analysis --------
    username = request.form["username"]
    github_raw = subprocess.getoutput(f'python github_analyzer.py "{username}"')

    verified_skills = [
        line.split()[0].lower()
        for line in github_raw.split("\n")
        if "Score:" in line and "Weak" not in line
    ]

    # -------- Skill Gap --------
    role = request.form["role"]
    gap_raw = subprocess.getoutput(f'python skill_gap.py "{role}"')

    strong, moderate, missing = [], [], []
    section = None

    for line in gap_raw.split("\n"):
        if "Strong Skills" in line:
            section = "strong"
        elif "Moderate Skills" in line:
            section = "moderate"
        elif "Missing Skills" in line:
            section = "missing"
        elif line.strip().startswith("-"):
            skill_name = line.strip()[2:]
            if section == "strong":
                strong.append(skill_name)
            elif section == "moderate":
                moderate.append(skill_name)
            elif section == "missing":
                missing.append(skill_name)

    # -------- Score Meter --------
    skill_scores = {}
    for s in strong: skill_scores[s] = 90
    for s in moderate: skill_scores[s] = 60
    for s in missing: skill_scores[s] = 20

    # -------- Recommendations --------
    PROJECT_MAP = {
        "react": "Build a Personal Portfolio SPA with React",
        "node": "Create a REST API backend using Node.js",
        "sql": "Develop a Student Database Management System",
        "python": "Build a Data Analysis Automation Script",
        "machine learning": "Create a Prediction Model using ML",
        "javascript": "Build an Interactive Web Application",
        "html": "Design a Multi-page Responsive Website",
        "css": "Create a Modern UI Dashboard",
        "git": "Maintain a version-controlled team project"
    }

    recommendations = [
        PROJECT_MAP.get(skill, f"Build a project using {skill}")
        for skill in missing
    ]

    # -------- SAVE REPORT --------
    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO reports(user_id, role_target, strong, moderate, missing)
    VALUES(?,?,?,?,?)
    """, (
        session["user_id"],
        role,
        ",".join(strong),
        ",".join(moderate),
        ",".join(missing)
    ))

    report_id = cur.lastrowid
    conn.commit()

    # -------- FETCH TEACHER RATINGS --------
    rating_rows = cur.execute(
        "SELECT skill,rating FROM ratings WHERE report_id=?",
        (report_id,)
    ).fetchall()

    conn.close()

    teacher_ratings = {skill: rating for skill, rating in rating_rows}

    return render_template(
        "dashboard.html",
        resume=resume_skills,
        verified=verified_skills,
        strong=strong,
        moderate=moderate,
        missing=missing,
        scores=skill_scores,
        projects=recommendations,
        teacher=teacher_ratings
    )




# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
