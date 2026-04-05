import os
import sqlite3
from flask import Flask, render_template, request, session, redirect, jsonify
from werkzeug.utils import secure_filename
from database import init_db
from services import skill_analysis, github_analysis, matching_engine, roadmap_generator, progress_tracker

app = Flask(__name__)
app.secret_key = "skillgap_secret_key_pro"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize Database
init_db()

def get_db():
    conn = sqlite3.connect("skillgap.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def index():
    return render_template("index.html")

# ---------------- AUTH ROUTES ----------------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]
        
        db = get_db()
        try:
            db.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                       (name,email,password,role))
            db.commit()
            return redirect("/login")
        except Exception as e:
            print(f"Registration error: {e}")
            return "Email already exists"
        finally:
            db.close()
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=? AND password=?",
                         (email,password)).fetchone()
        db.close()
        
        if user:
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            return redirect("/dashboard")
        return "Invalid login"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    
    if session["role"] == "student":
        return render_template("student_dashboard.html")
    else:
        return render_template("teacher_dashboard.html")

@app.route("/discovery")
def discovery():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("discovery.html")

# ---------------- STUDENT FLOW ----------------
@app.route("/analyze_profile", methods=["POST"])
def analyze_profile():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session["user_id"]
    github_user = request.form.get("github_user")
    resume = request.files.get("resume")
    
    # Process Resume
    if resume:
        filename = secure_filename(resume.filename)
        path = os.path.join(UPLOAD_FOLDER, filename)
        resume.save(path)
        skill_ids = skill_analysis.extract_skills_from_pdf(path)
        skill_analysis.save_user_skills(user_id, skill_ids, 'resume')
    
    # Process GitHub
    if github_user:
        db = get_db()
        db.execute("UPDATE users SET github_username=? WHERE id=?", (github_user, user_id))
        db.commit()
        db.close()
        github_analysis.verify_github_skills(user_id, github_user)
        
    return jsonify({"success": True})

@app.route("/get_analysis")
def get_analysis():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session["user_id"]
    goal_role = request.args.get("goal", "Web Developer")
    
    analysis = skill_analysis.calculate_skill_gap(user_id, goal_role)
    if not analysis:
        return jsonify({"error": "No skills analyzed yet"}), 200
        
    return jsonify(analysis)

@app.route("/request_mentorship", methods=["POST"])
def request_mentorship():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    db.execute("""
        INSERT INTO mentorship_requests(student_id, goal_role, project_idea) 
        VALUES(?,?,?)
    """, (session["user_id"], request.form["goal_role"], request.form["project_idea"]))
    db.commit()
    db.close()
    return jsonify({"success": True})

@app.route("/get_matches")
def get_matches():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    matches = matching_engine.match_student_with_teachers(session["user_id"])
    return jsonify({"matches": matches})

@app.route("/generate-roadmap", methods=["POST"])
def generate_roadmap():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = session["user_id"]
    goal_role = request.form.get("goal_role")
    
    # Needs to get missing and moderate skills
    analysis = skill_analysis.calculate_skill_gap(user_id, goal_role)
    if not analysis:
         return jsonify({"error": "Analysis not ready"})
         
    missing = [m["name"] for m in analysis["missing"]]
    moderate = [m["name"] for m in analysis["moderate"]]
    
    rm = roadmap_generator.generate_roadmap(user_id, goal_role, missing, moderate)
    return jsonify({"success": True, "roadmap": rm})

@app.route("/get-roadmap")
def get_roadmap():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    rm = roadmap_generator.get_user_roadmap(session["user_id"])
    if not rm:
        return jsonify({"error": "No roadmap found"})
    return jsonify(rm)

@app.route("/update-progress", methods=["POST"])
def update_progress():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    step_id = request.form.get("step_id")
    status = request.form.get("status")
    roadmap_generator.update_step_status(step_id, status)
    return jsonify({"success": True})

@app.route("/get-skill-history")
def get_skill_history():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    growth = progress_tracker.get_growth_indicators(session["user_id"])
    return jsonify({"history": growth})

# ---------------- COLLABORATION / GROUPS ----------------
@app.route("/create_group", methods=["POST"])
def create_group():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    name = request.form.get("name")
    project_title = request.form.get("project_title")
    description = request.form.get("description")
    user_id = session["user_id"]
    
    db = get_db()
    cursor = db.execute("""
        INSERT INTO student_groups(name, project_title, description, leader_id)
        VALUES(?,?,?,?)
    """, (name, project_title, description, user_id))
    group_id = cursor.lastrowid
    
    # Add leader to group
    db.execute("""
        INSERT INTO student_group_members(group_id, student_id)
        VALUES(?,?)
    """, (group_id, user_id))
    db.commit()
    db.close()
    
    return jsonify({"success": True, "group_id": group_id})

@app.route("/join_group", methods=["POST"])
def join_group():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    group_id = request.form.get("group_id")
    user_id = session["user_id"]
    
    db = get_db()
    try:
        db.execute("INSERT INTO student_group_members(group_id, student_id) VALUES(?,?)", (group_id, user_id))
        db.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False # Already joined
    db.close()
    
    return jsonify({"success": success})

@app.route("/update_project_status", methods=["POST"])
def update_project_status():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    group_id = request.form.get("group_id")
    message = request.form.get("message")
    status = request.form.get("status")
    
    db = get_db()
    if status:
        db.execute("UPDATE student_groups SET status=? WHERE id=?", (status, group_id))
    if message:
        db.execute("INSERT INTO project_updates(group_id, message) VALUES(?,?)", (group_id, message))
    db.commit()
    db.close()
    
    return jsonify({"success": True})

@app.route("/get_groups")
def get_groups():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    # Fetch all groups
    groups = db.execute("""
        SELECT g.*, u.name as leader_name 
        FROM student_groups g
        JOIN users u ON u.id = g.leader_id
        ORDER BY g.created_at DESC
    """).fetchall()
    
    result = []
    for g in groups:
        g_dict = dict(g)
        members = db.execute("""
            SELECT u.id, u.name 
            FROM student_group_members m
            JOIN users u ON u.id = m.student_id
            WHERE m.group_id = ?
        """, (g["id"],)).fetchall()
        
        updates = db.execute("""
            SELECT * FROM project_updates 
            WHERE group_id = ? 
            ORDER BY timestamp DESC LIMIT 3
        """, (g["id"],)).fetchall()
        
        g_dict["members"] = [dict(m) for m in members]
        g_dict["updates"] = [dict(u) for u in updates]
        result.append(g_dict)
        
    db.close()
    return jsonify({"groups": result})

@app.route("/get_students")
def get_students():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    db = get_db()
    # Fetch all students and their availability
    students = db.execute("""
        SELECT u.id, u.name, u.bio, u.avatar, IFNULL(sa.status, 'Available') as availability
        FROM users u
        LEFT JOIN student_availability sa ON sa.user_id = u.id
        WHERE u.role = 'student'
    """).fetchall()
    db.close()
    
    return jsonify({"students": [dict(s) for s in students]})

# ---------------- TEACHER FLOW ----------------
@app.route("/get_incoming_requests")
def get_incoming_requests():
    if "user_id" not in session or session["role"] != "teacher":
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    reqs = db.execute("""
        SELECT r.id, u.name as student_name, r.goal_role, r.project_idea, r.status
        FROM mentorship_requests r
        JOIN users u ON u.id = r.student_id
        WHERE r.status = 'pending'
    """).fetchall()
    db.close()
    
    return jsonify({"requests": [dict(r) for r in reqs]})

@app.route("/accept_request", methods=["POST"])
def accept_request():
    if "user_id" not in session or session["role"] != "teacher":
        return jsonify({"error": "Unauthorized"}), 401
    
    req_id = request.form["request_id"]
    db = get_db()
    db.execute("UPDATE mentorship_requests SET status = 'matched' WHERE id = ?", (req_id,))
    db.commit()
    db.close()
    return jsonify({"success": True})

# ---------------- CHAT ----------------
@app.route("/send_message", methods=["POST"])
def send_message():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    db.execute("""
        INSERT INTO messages(sender_id, receiver_id, message) 
        VALUES(?,?,?)
    """, (session["user_id"], request.form["receiver_id"], request.form["message"]))
    db.commit()
    db.close()
    return jsonify({"success": True})

@app.route("/get_messages")
def get_messages():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    other_id = request.args.get("other_id")
    db = get_db()
    msgs = db.execute("""
        SELECT * FROM messages 
        WHERE (sender_id = ? AND receiver_id = ?) 
           OR (sender_id = ? AND receiver_id = ?)
        ORDER BY timestamp ASC
    """, (session["user_id"], other_id, other_id, session["user_id"])).fetchall()
    db.close()
    
    return jsonify({"messages": [dict(m) for m in msgs]})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
