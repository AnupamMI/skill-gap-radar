from flask import Flask, render_template, request, session, redirect, jsonify
import subprocess
import os
import sqlite3
from datetime import datetime
from werkzeug.utils import secure_filename

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
            "id": report_id,
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

# ---------------- MESSAGES ----------------
@app.route("/messages")
def messages_home():
    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()

    users = cur.execute("""
        SELECT id, name, role FROM users
        WHERE id != ?
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template("messages.html", users=users)


@app.route("/messenger")
def messenger():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()

    chats = cur.execute("""
    SELECT conversations.id, users.name
    FROM conversations
    JOIN participants ON conversations.id = participants.conversation_id
    JOIN users ON users.id = participants.user_id
    WHERE conversations.id IN (
        SELECT conversation_id FROM participants WHERE user_id=?
    ) AND users.id != ?
    """,(session["user_id"],session["user_id"])).fetchall()

    conn.close()

    return render_template("messenger.html", chats=chats)


@app.route("/start_chat/<int:user_id>")
def start_chat(user_id):

    if "user_id" not in session:
        return redirect("/login")

    me = session["user_id"]

    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()

    # Find existing PRIVATE conversation between 2 users
    conv = cur.execute("""
    SELECT c.id
    FROM conversations c
    JOIN participants p1 ON c.id = p1.conversation_id
    JOIN participants p2 ON c.id = p2.conversation_id
    WHERE c.is_group = 0
      AND p1.user_id = ?
      AND p2.user_id = ?
    """,(me,user_id)).fetchone()

    if conv:
        cid = conv[0]
    else:
        # Create new conversation
        cur.execute("INSERT INTO conversations(is_group,name) VALUES(0,NULL)")
        cid = cur.lastrowid

        cur.execute("INSERT INTO participants(conversation_id,user_id) VALUES(?,?)",(cid,me))
        cur.execute("INSERT INTO participants(conversation_id,user_id) VALUES(?,?)",(cid,user_id))

        conn.commit()

    conn.close()

    return redirect(f"/chatroom/{cid}")
@app.route("/chatroom/<int:cid>")
def chatroom(cid):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()

    allowed = cur.execute("""
    SELECT 1 FROM participants
    WHERE conversation_id=? AND user_id=?
    """,(cid,session["user_id"])).fetchone()

    if not allowed:
        conn.close()
        return "Unauthorized"

    messages = cur.execute("""
    SELECT users.name, messages.message, messages.timestamp, messages.sender_id
    FROM messages
    JOIN users ON users.id = messages.sender_id
    WHERE conversation_id=?
    ORDER BY messages.id
    """,(cid,)).fetchall()

    conn.close()

    return render_template("chatroom.html", messages=messages, cid=cid)


# -------- GET MESSAGES (AJAX) --------
@app.route("/get_messages/<int:cid>")
def get_messages(cid):
    
    if "user_id" not in session:
        return redirect("/login")
    
    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()
    
    # Verify access
    allowed = cur.execute("""
        SELECT 1 FROM participants
        WHERE conversation_id=? AND user_id=?
    """, (cid, session["user_id"])).fetchone()
    
    if not allowed:
        conn.close()
        return "Unauthorized"
    
    messages = cur.execute("""
        SELECT users.name, messages.message, messages.timestamp, messages.sender_id, messages.media
        FROM messages
        JOIN users ON users.id = messages.sender_id
        WHERE conversation_id=?
        ORDER BY messages.id ASC
    """, (cid,)).fetchall()
    
    conn.close()
    
    html = ""
    for name, msg, timestamp, sender_id, media in messages:
        is_me = "sent" if sender_id == session["user_id"] else "received"
        time_str = timestamp.split()[1][:5] if timestamp else ""
        
        html += f'''
        <div class="message {is_me}">
            {f'<div class="sender-name">{name}</div>' if is_me == "received" else ''}
            <div class="message-bubble">
                {msg}
                {f'<div class="file-preview">📎 {media}</div>' if media else ''}
            </div>
            <div class="message-meta">{time_str} ✓</div>
        </div>
        '''
    
    return html


# -------- UPLOAD MEDIA --------
@app.route("/upload_media", methods=["POST"])
def upload_media():
    
    if "user_id" not in session:
        return jsonify({"success": False})
    
    cid = request.form.get("cid")
    file = request.files.get("file")
    
    if not file:
        return jsonify({"success": False})
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO messages(conversation_id, sender_id, message, media)
        VALUES(?, ?, ?, ?)
    """, (cid, session["user_id"], f"Shared a file", filename))
    
    conn.commit()
    conn.close()
    
    return jsonify({"success": True})


@app.route("/send_chat", methods=["POST"])
def send_chat():
    
    cid = request.form.get("cid")
    msg = request.form.get("msg")
    
    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO messages(conversation_id, sender_id, message)
        VALUES(?, ?, ?)
    """, (cid, session["user_id"], msg))
    
    conn.commit()
    conn.close()
    
    return redirect(f"/chatroom/{cid}")


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

    # -------- SAVE OR UPDATE REPORT --------
    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()

    existing = cur.execute("""
        SELECT id FROM reports
        WHERE user_id=? AND role_target=?
    """,(session["user_id"],role)).fetchone()

    if existing:
        report_id = existing[0]

        cur.execute("""
        UPDATE reports
        SET strong=?, moderate=?, missing=?
        WHERE id=?
        """,(",".join(strong),",".join(moderate),",".join(missing),report_id))

    else:
        cur.execute("""
        INSERT INTO reports(user_id, role_target, strong, moderate, missing)
        VALUES(?,?,?,?,?)
        """,(session["user_id"],role,",".join(strong),",".join(moderate),",".join(missing)))

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
