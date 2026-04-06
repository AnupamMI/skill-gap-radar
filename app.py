import os
import sqlite3
import json
from openai import OpenAI
from flask import Flask, render_template, request, session, redirect, jsonify
from werkzeug.utils import secure_filename
from database import init_db
from services import matching_engine
from services.analysis_engine import (
    extract_skills_from_text, enrich_with_github, build_roadmap, ROLES_CONFIG
)

app = Flask(__name__)
app.secret_key = "skillgap_secret_key_pro"

# Groq Client (OpenAI-compatible)
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("GROQ_API_KEY is not set")

groq_client = OpenAI(
    api_key=api_key,
    base_url="https://api.groq.com/openai/v1"
)

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

@app.errorhandler(404)
def not_found(e):
    return redirect("/dashboard")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
@app.route("/<section>")
def dashboard(section='dashboard'):
    if "user_id" not in session:
        if section != 'dashboard': return redirect("/login")
        return render_template("index.html") # Landing page for non-logged-in
    
    allowed_student = ['dashboard', 'radar', 'roadmap', 'groups', 'discovery']
    allowed_teacher = ['dashboard', 'requests', 'groups', 'discovery']
    
    role = session.get('role', 'student')
    
    if role == 'student':
        if section not in allowed_student: return redirect("/dashboard")
        
        # Dashboard or Roadmap requires an active analysis session
        analysis_data = session.get('analysis')
        if not analysis_data and section in ['dashboard', 'roadmap']:
            return redirect("/radar")
            
        return render_template("student_dashboard.html", active=section, analysis=analysis_data)
    else:
        # For teacher, map routes to sections
        if section == 'dashboard': section = 'dashboard'
        elif section == 'requests': section = 'requests'
        elif section not in allowed_teacher: return redirect("/dashboard")
        return render_template("teacher_dashboard.html", active=section)

@app.route("/discovery_old") # Renaming old route to avoid conflict
def discovery_old():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("discovery.html")

# ---------------- STUDENT FLOW ----------------
@app.route("/analyze", methods=["POST"])
def analyze():
    # ── Step 1: Extract text from PDF ────────────────────────────────────────
    goal_role    = request.form.get("goal_role", "Web Developer")
    resume_file  = request.files.get("resume")
    github_user  = request.form.get("github_user", "").strip()

    raw_text = ""
    if resume_file and resume_file.filename:
        filename = secure_filename(resume_file.filename)
        path = os.path.join(UPLOAD_FOLDER, filename)
        resume_file.save(path)
        try:
            from pdfminer.high_level import extract_text as pdf_extract
            raw_text = pdf_extract(path) or ""
            print(f"[analyze] PDF extracted: {len(raw_text)} chars")
        except Exception as e:
            print(f"[analyze] PDF extraction error: {e}")

    if not raw_text:
        print("[analyze] No resume text — proceeding with empty resume (GitHub only or default)")

    # ── Step 2: Run skill extraction engine ──────────────────────────────────
    analysis = extract_skills_from_text(raw_text, goal_role)
    print(f"[analyze] Matched: {analysis['matched_skills']} | Missing: {analysis['missing_skills']}")

    # ── Step 3: Enrich with GitHub (optional) ────────────────────────────────
    if github_user:
        analysis = enrich_with_github(analysis, github_user)
        print(f"[analyze] After GitHub: {analysis['matched_skills']}")

    # ── Step 4: Build structured roadmap ─────────────────────────────────────
    analysis["roadmap"] = build_roadmap(analysis)

    # ── Step 5: Store everything in session ──────────────────────────────────
    session["analysis"] = analysis
    print(f"[analyze] Stored to session. Score={analysis['match_score']}%")

    # ── Step 6: Save to analytics history ────────────────────────────────────
    try:
        # Calculate skill breakdown by domain for radar chart
        skill_breakdown = {
            "frontend": calculate_domain_score(analysis.get("matched_skills", []), "frontend"),
            "backend": calculate_domain_score(analysis.get("matched_skills", []), "backend"),
            "dsa": calculate_domain_score(analysis.get("matched_skills", []), "dsa"),
            "ml": calculate_domain_score(analysis.get("matched_skills", []), "ml"),
            "devops": calculate_domain_score(analysis.get("matched_skills", []), "devops")
        }
        
        db = get_db()
        db.execute("""
            INSERT INTO user_analysis_history 
            (user_id, total_score, skill_breakdown, matched_skills, missing_skills, analysis_source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            session.get("user_id") or 0,
            len(analysis.get("matched_skills", [])),
            json.dumps(skill_breakdown),
            json.dumps(analysis.get("matched_skills", [])),
            json.dumps(analysis.get("missing_skills", [])),
            "combined" if github_user else "resume"
        ))
        db.commit()
        db.close()
        print(f"[analyze] Saved to analytics history")
    except Exception as e:
        print(f"[analyze] Error saving to history: {e}")

    return redirect("/radar")


def call_groq(system_prompt, messages):
    """Call Groq's Llama3-70b via OpenAI-compatible client."""
    try:
        # Build message list with system prompt prepended
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        response = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=full_messages,
            max_tokens=600,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        err_str = str(e).lower()
        print(f"Groq API Error: {e}")
        if "invalid_api_key" in err_str or "authentication" in err_str:
            return "⚠️ Invalid Groq API key. Please update the key in app.py."
        elif "rate" in err_str:
            return "⚠️ Groq rate limit hit. Please wait a moment and try again."
        else:
            return f"⚠️ AI Mentor is temporarily unavailable. Please try again shortly."

@app.route("/chat", methods=["POST"])
def chat():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Validation — must have run an analysis first
    analysis = session.get('analysis')
    if not analysis:
        return jsonify({"error": "No analysis found. Run a resume scan first."}), 400

    data = request.get_json()
    message = data.get("message", "").strip()
    history = data.get("history", [])

    role = analysis.get("role", "Engineer")
    matched_skills = analysis.get("matched_skills", [])
    missing_skills = analysis.get("missing_skills", [])
    match_score = analysis.get("match_score", 0)

    # Dynamic system prompt built entirely from session data
    system_prompt = f"""You are a personal career mentor for a candidate targeting: {role}.
Verified skills: {', '.join(matched_skills) if matched_skills else 'none yet'} — {match_score:.0f}% role match.
Skill gaps to close: {', '.join(missing_skills) if missing_skills else 'none — fully qualified!'}.

Rules:
- Always ground advice in the skill gaps above. Never give generic career tips.
- "what should I learn next" → name the top 1-2 skills from the gap list with a concrete reason why for a {role}.
- "suggest a project" → propose a project that uses at least 2 skills from the gap list.
- "explain [X]" → brief explanation + connect it to their {role} roadmap.
- "review my resume" → ask them to paste specific sections, then give targeted gap-based feedback.
- All else → answer with their {role} context and gap list in mind. Be direct and specific."""

    # Build conversation history for multi-turn context
    conversation = []
    for h in history:
        role_label = "user" if h["sender"] == "user" else "assistant"
        conversation.append({"role": role_label, "content": h["text"]})
    
    if message:
        conversation.append({"role": "user", "content": message})
        
    reply_text = call_groq(system_prompt, conversation)
    return jsonify({"reply": reply_text})

@app.route("/switch-role", methods=["POST"])
def switch_role():
    if 'analysis' not in session:
        return jsonify({"error": "No analysis exists to switch."}), 400

    new_role = request.form.get("new_role")
    if new_role not in ROLES_CONFIG:
        return jsonify({"error": "Invalid role"}), 400

    # Re-run roadmap generation against the new role using the original matched skills
    prev = session['analysis']
    raw_matched = prev.get('matched_skills', [])  # skills already proven from resume/github

    # Re-analyse using only matched skills text representation
    fake_text = " ".join(raw_matched)  # build a pseudo text of known skills
    analysis = extract_skills_from_text(fake_text, new_role)

    # Preserve GitHub enrichment if it was done before
    gh_user = prev.get("github_username", "")
    if gh_user:
        analysis = enrich_with_github(analysis, gh_user)

    analysis["roadmap"] = build_roadmap(analysis)
    session['analysis'] = analysis

    return jsonify({"success": True, "analysis": {
        "role":           analysis["role"],
        "match_score":    analysis["match_score"],
        "matched_skills": analysis["matched_skills"],
        "missing_skills": analysis["missing_skills"],
    }})

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


# ==================== PHASE 4: COLLABORATION NETWORK ====================

# 1. ENHANCED GROUP CREATION (with project link)
@app.route("/student/groups", methods=["POST"])
def create_student_group():
    """Create a new student group with optional project link."""
    if "user_id" not in session or session.get("role") != "student":
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    name = data.get("name", "").strip()
    project_title = data.get("project_title", "").strip()
    project_id = data.get("project_id")
    goal = data.get("goal", "").strip()
    description = data.get("description", "").strip()
    max_members = data.get("max_members", 5)
    
    if not name:
        return jsonify({"error": "Group name is required"}), 400
    
    db = get_db()
    
    if project_id:
        application = db.execute(
            "SELECT * FROM applications WHERE project_id = ? AND student_id = ? AND status = 'accepted'",
            (project_id, session["user_id"])
        ).fetchone()
        if not application:
            db.close()
            return jsonify({"error": "You must be accepted to the project to create a group"}), 403
    
    cursor = db.execute("""
        INSERT INTO student_groups(name, project_title, project_id, goal, description, leader_id, max_members, status)
        VALUES(?, ?, ?, ?, ?, ?, ?, 'active')
    """, (name, project_title, project_id, goal, description, session["user_id"], max_members))
    group_id = cursor.lastrowid
    
    db.execute("""
        INSERT INTO student_group_members(group_id, student_id, role)
        VALUES(?, ?, 'leader')
    """, (group_id, session["user_id"]))
    
    db.execute("""
        INSERT OR REPLACE INTO student_availability(user_id, status, looking_for, last_updated)
        VALUES(?, 'busy', 'project', CURRENT_TIMESTAMP)
    """, (session["user_id"],))
    
    db.commit()
    db.close()
    
    return jsonify({"success": True, "group_id": group_id})


# 2. GET MY GROUPS (for student)
@app.route("/student/my-groups", methods=["GET"])
def get_my_groups():
    """Get all groups where student is a member."""
    if "user_id" not in session or session.get("role") != "student":
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    groups = db.execute("""
        SELECT g.*, p.title as linked_project_title, p.faculty_id,
               u.name as leader_name,
               (SELECT COUNT(*) FROM student_group_members WHERE group_id = g.id) as member_count
        FROM student_groups g
        JOIN student_group_members m ON m.group_id = g.id
        LEFT JOIN projects p ON p.id = g.project_id
        JOIN users u ON u.id = g.leader_id
        WHERE m.student_id = ?
        ORDER BY g.created_at DESC
    """, (session["user_id"],)).fetchall()
    
    result = []
    for g in groups:
        members = db.execute("""
            SELECT u.id, u.name, u.bio, m.role,
                   (SELECT GROUP_CONCAT(s.name) FROM user_skills us 
                    JOIN skills s ON s.id = us.skill_id WHERE us.user_id = u.id) as skills
            FROM student_group_members m
            JOIN users u ON u.id = m.student_id
            WHERE m.group_id = ?
        """, (g["id"],)).fetchall()
        
        g_dict = dict(g)
        g_dict["members"] = [dict(m) for m in members]
        g_dict["is_leader"] = g["leader_id"] == session["user_id"]
        result.append(g_dict)
    
    db.close()
    return jsonify({"groups": result})


# 3. DISCOVERY NETWORK
@app.route("/discovery/network", methods=["GET"])
def get_discovery_network():
    """Get discovery network: students, groups, projects."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    
    # Get students
    students = db.execute("""
        SELECT u.id, u.name, u.bio, u.avatar,
               IFNULL(sa.status, 'available') as availability,
               sa.looking_for,
               (SELECT GROUP_CONCAT(s.name) FROM user_skills us 
                JOIN skills s ON s.id = us.skill_id WHERE us.user_id = u.id) as skills
        FROM users u
        LEFT JOIN student_availability sa ON sa.user_id = u.id
        WHERE u.role = 'student' AND u.id != ?
        ORDER BY u.name
    """, (session["user_id"],)).fetchall()
    
    # Get active groups
    groups = db.execute("""
        SELECT g.*, p.title as linked_project_title, u.name as leader_name,
               (SELECT COUNT(*) FROM student_group_members WHERE group_id = g.id) as member_count
        FROM student_groups g
        LEFT JOIN projects p ON p.id = g.project_id
        JOIN users u ON u.id = g.leader_id
        WHERE g.status = 'active'
        ORDER BY g.created_at DESC
    """).fetchall()
    
    group_list = []
    for g in groups:
        members = db.execute("""
            SELECT u.id, u.name FROM student_group_members m
            JOIN users u ON u.id = m.student_id
            WHERE m.group_id = ?
        """, (g["id"],)).fetchall()
        
        g_dict = dict(g)
        g_dict["members"] = [dict(m) for m in members]
        g_dict["is_member"] = any(m["id"] == session["user_id"] for m in members)
        group_list.append(g_dict)
    
    # Get open projects
    projects = db.execute("""
        SELECT p.*, u.name as faculty_name
        FROM projects p
        JOIN users u ON u.id = p.faculty_id
        WHERE p.status = 'open'
        ORDER BY p.posted_at DESC
    """).fetchall()
    
    project_list = []
    for p in projects:
        p_dict = dict(p)
        p_dict["required_skills"] = json.loads(p["required_skills"]) if p["required_skills"] else []
        project_list.append(p_dict)
    
    db.close()
    
    return jsonify({
        "students": [dict(s) for s in students],
        "groups": group_list,
        "projects": project_list
    })


# 4. TEACHER GROUP MONITORING
@app.route("/teacher/groups", methods=["GET"])
def get_teacher_groups():
    """Get all student groups for teacher monitoring."""
    if "user_id" not in session or session.get("role") != "teacher":
        return jsonify({"error": "Unauthorized"}), 401
    
    filter_status = request.args.get("status", "")
    
    db = get_db()
    
    query = """
        SELECT g.*, p.title as linked_project_title, u.name as leader_name,
               (SELECT COUNT(*) FROM student_group_members WHERE group_id = g.id) as member_count,
               (SELECT COUNT(*) FROM project_updates WHERE group_id = g.id) as update_count,
               tge.is_shortlisted, tge.is_high_potential, tge.avg_match_score
        FROM student_groups g
        LEFT JOIN projects p ON p.id = g.project_id
        JOIN users u ON u.id = g.leader_id
        LEFT JOIN teacher_group_evaluations tge ON tge.group_id = g.id AND tge.teacher_id = ?
        WHERE 1=1
    """
    params = [session["user_id"]]
    
    if filter_status:
        query += " AND g.status = ?"
        params.append(filter_status)
    
    query += " ORDER BY g.created_at DESC"
    
    groups = db.execute(query, params).fetchall()
    
    result = []
    for g in groups:
        members = db.execute("""
            SELECT u.id, u.name FROM student_group_members m
            JOIN users u ON u.id = m.student_id
            WHERE m.group_id = ?
        """, (g["id"],)).fetchall()
        
        g_dict = dict(g)
        g_dict["members"] = [dict(m) for m in members]
        g_dict["activity_level"] = "high" if g["update_count"] > 10 else "medium" if g["update_count"] > 5 else "low"
        result.append(g_dict)
    
    db.close()
    return jsonify({"groups": result})


# 5. EVALUATE GROUP
@app.route("/teacher/groups/<int:group_id>/evaluate", methods=["POST"])
def evaluate_group(group_id):
    """Teacher evaluates a group."""
    if "user_id" not in session or session.get("role") != "teacher":
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    is_shortlisted = data.get("is_shortlisted", False)
    is_high_potential = data.get("is_high_potential", False)
    notes = data.get("notes", "").strip()
    
    db = get_db()
    
    avg_match = db.execute("""
        SELECT AVG(a.match_score) as avg_score
        FROM applications a
        JOIN student_group_members m ON m.student_id = a.student_id
        JOIN student_groups g ON g.project_id = a.project_id
        WHERE g.id = ? AND a.status = 'accepted'
    """, (group_id,)).fetchone()
    
    avg_score = int(avg_match["avg_score"]) if avg_match and avg_match["avg_score"] else 0
    
    db.execute("""
        INSERT INTO teacher_group_evaluations 
        (group_id, teacher_id, is_shortlisted, is_high_potential, avg_match_score, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(group_id, teacher_id) DO UPDATE SET
        is_shortlisted = excluded.is_shortlisted,
        is_high_potential = excluded.is_high_potential,
        avg_match_score = excluded.avg_match_score,
        notes = excluded.notes,
        evaluated_at = CURRENT_TIMESTAMP
    """, (group_id, session["user_id"], 1 if is_shortlisted else 0, 1 if is_high_potential else 0, avg_score, notes))
    
    db.commit()
    db.close()
    
    return jsonify({"success": True})


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


# ---------------- FACULTY-STUDENT MATCHING (PHASE 3) ----------------

def compute_match(student_skills, required_skills):
    """Calculate match score between student skills and project requirements."""
    s = set(x.lower().strip() for x in student_skills)
    r = set(x.lower().strip() for x in required_skills)
    overlap = s & r
    missing = r - s
    score = round((len(overlap) / len(r)) * 100) if r else 0
    return score, list(overlap), list(missing)


def generate_match_reason(student_skills, required_skills, match_score):
    """Call LLM to generate match reason using the Groq client."""
    system_prompt = "You are a faculty assistant reviewing student-project fit. Write exactly one sentence (under 15 words) naming specific matching skills and explaining why this student fits. If match is weak, say so honestly."
    user_message = f"Student skills: {', '.join(student_skills)}. Project needs: {', '.join(required_skills)}. Match score: {match_score}%."
    
    try:
        response = call_groq(system_prompt, [{"role": "user", "content": user_message}])
        return response.strip()
    except Exception as e:
        print(f"LLM reason generation failed: {e}")
        return "Skill overlap identified, reason unavailable"


# 1. POST /faculty/post-project
@app.route("/faculty/post-project", methods=["POST"])
def post_project():
    if "user_id" not in session or session.get("role") != "teacher":
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    title = data.get("title", "").strip()
    description = data.get("description", "").strip()
    required_skills = data.get("required_skills", [])
    
    if not title:
        return jsonify({"error": "Title is required"}), 400
    if len(required_skills) < 2:
        return jsonify({"error": "At least 2 required skills are needed"}), 400
    
    db = get_db()
    cursor = db.execute(
        "INSERT INTO projects (faculty_id, title, description, required_skills) VALUES (?, ?, ?, ?)",
        (session["user_id"], title, description, json.dumps(required_skills))
    )
    project_id = cursor.lastrowid
    db.commit()
    db.close()
    
    return jsonify({"project_id": project_id, "title": title})


# 2. GET /faculty/projects
@app.route("/faculty/projects", methods=["GET"])
def get_faculty_projects():
    if "user_id" not in session or session.get("role") != "teacher":
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    projects = db.execute(
        "SELECT id, title, description, required_skills, posted_at FROM projects WHERE faculty_id = ? AND status = 'open'",
        (session["user_id"],)
    ).fetchall()
    db.close()
    
    result = []
    for p in projects:
        result.append({
            "id": p["id"],
            "title": p["title"],
            "description": p["description"],
            "required_skills": json.loads(p["required_skills"]) if p["required_skills"] else [],
            "posted_at": p["posted_at"]
        })
    return jsonify(result)


# 3. GET /faculty/matches/<project_id>
@app.route("/faculty/matches/<int:project_id>", methods=["GET"])
def get_faculty_matches(project_id):
    if "user_id" not in session or session.get("role") != "teacher":
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    
    # Load project
    project = db.execute(
        "SELECT * FROM projects WHERE id = ? AND faculty_id = ?",
        (project_id, session["user_id"])
    ).fetchone()
    
    if not project:
        db.close()
        return jsonify({"error": "Project not found"}), 404
    
    required_skills = json.loads(project["required_skills"]) if project["required_skills"] else []
    
    # Load all students with skill profiles from session analysis
    # Note: In production, this would come from a stored skills table
    # For now, we look for students who have analysis data in their sessions
    # We'll simulate by checking users table for students
    students = db.execute(
        "SELECT id, name FROM users WHERE role = 'student'"
    ).fetchall()
    
    matches = []
    for student in students:
        # Get student's skills - in a real system these would be stored in DB
        # For demo, we'll use a simplified approach - check if student has applied
        application = db.execute(
            "SELECT * FROM applications WHERE project_id = ? AND student_id = ?",
            (project_id, student["id"])
        ).fetchone()
        
        if application and application["student_skills"]:
            student_skills = json.loads(application["student_skills"])
        else:
            # Default empty skills if no application yet
            student_skills = []
        
        score, matched, missing = compute_match(student_skills, required_skills)
        
        # Check for cached reason
        reason = None
        if application and application["match_reason"]:
            reason = application["match_reason"]
        
        matches.append({
            "student_id": student["id"],
            "student_name": student["name"],
            "match_score": score,
            "matched_skills": matched,
            "missing_skills": missing,
            "match_reason": reason,
            "has_application": application is not None
        })
    
    # Sort by score descending, take top 5
    matches.sort(key=lambda x: x["match_score"], reverse=True)
    top_matches = matches[:5]
    
    # Generate LLM reasons for top 5 if not cached
    for match in top_matches:
        if not match["match_reason"]:
            # Get student skills for LLM call
            student_skills = []
            for s in students:
                if s["id"] == match["student_id"]:
                    app_record = db.execute(
                        "SELECT student_skills FROM applications WHERE project_id = ? AND student_id = ?",
                        (project_id, s["id"])
                    ).fetchone()
                    if app_record and app_record["student_skills"]:
                        student_skills = json.loads(app_record["student_skills"])
                    break
            
            reason = generate_match_reason(
                match["matched_skills"] if match["matched_skills"] else student_skills,
                required_skills,
                match["match_score"]
            )
            match["match_reason"] = reason
            
            # Cache the reason if there's an application
            db.execute(
                "UPDATE applications SET match_reason = ? WHERE project_id = ? AND student_id = ?",
                (reason, project_id, match["student_id"])
            )
            db.commit()
    
    db.close()
    
    # Format response
    result = []
    for m in top_matches:
        result.append({
            "student_id": m["student_id"],
            "student_name": m["student_name"],
            "match_score": m["match_score"],
            "match_reason": m["match_reason"] or "Skill overlap identified, reason unavailable",
            "matched_skills": m["matched_skills"],
            "missing_skills": m["missing_skills"]
        })
    
    return jsonify(result)


# 4. GET /student/projects
@app.route("/student/projects", methods=["GET"])
def get_student_projects():
    if "user_id" not in session or session.get("role") != "student":
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    projects = db.execute(
        "SELECT id, title, description, required_skills, posted_at FROM projects WHERE status = 'open'"
    ).fetchall()
    
    # Check which projects student has applied to
    applications = db.execute(
        "SELECT project_id, match_score, status FROM applications WHERE student_id = ?",
        (session["user_id"],)
    ).fetchall()
    applied_project_ids = {a["project_id"]: {"match_score": a["match_score"], "status": a["status"]} for a in applications}
    
    db.close()
    
    result = []
    for p in projects:
        result.append({
            "id": p["id"],
            "title": p["title"],
            "description": p["description"],
            "required_skills": json.loads(p["required_skills"]) if p["required_skills"] else [],
            "posted_at": p["posted_at"],
            "applied": p["id"] in applied_project_ids,
            "match_score": applied_project_ids[p["id"]]["match_score"] if p["id"] in applied_project_ids else None,
            "status": applied_project_ids[p["id"]]["status"] if p["id"] in applied_project_ids else None
        })
    return jsonify(result)


# 5. POST /student/apply/<project_id>
@app.route("/student/apply/<int:project_id>", methods=["POST"])
def apply_to_project(project_id):
    if "user_id" not in session or session.get("role") != "student":
        return jsonify({"error": "Unauthorized"}), 401
    
    # Check for session analysis
    analysis = session.get("analysis")
    if not analysis:
        return jsonify({"error": "Complete your skill analysis before applying"}), 400
    
    data = request.get_json()
    project_idea = data.get("project_idea", "").strip()
    interest_statement = data.get("interest_statement", "").strip()
    
    db = get_db()
    
    # Check if project exists
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not project:
        db.close()
        return jsonify({"error": "Project not found"}), 404
    
    # Check for duplicate application
    existing = db.execute(
        "SELECT * FROM applications WHERE project_id = ? AND student_id = ?",
        (project_id, session["user_id"])
    ).fetchone()
    if existing:
        db.close()
        return jsonify({"error": "You have already applied to this project"}), 409
    
    # Get student skills from session
    student_skills = analysis.get("matched_skills", [])
    required_skills = json.loads(project["required_skills"]) if project["required_skills"] else []
    
    # Compute match
    score, matched, missing = compute_match(student_skills, required_skills)
    
    # Generate match reason via LLM
    reason = generate_match_reason(matched, required_skills, score)
    
    # Insert application
    cursor = db.execute(
        """INSERT INTO applications 
           (project_id, student_id, student_name, student_skills, project_idea, interest_statement, match_score, match_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (project_id, session["user_id"], session.get("name", ""), json.dumps(student_skills),
         project_idea, interest_statement, score, reason)
    )
    application_id = cursor.lastrowid
    db.commit()
    db.close()
    
    return jsonify({
        "application_id": application_id,
        "match_score": score,
        "match_reason": reason
    })


# 6. GET /faculty/applications/<project_id>
@app.route("/faculty/applications/<int:project_id>", methods=["GET"])
def get_faculty_applications(project_id):
    if "user_id" not in session or session.get("role") != "teacher":
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    
    # Verify project ownership
    project = db.execute(
        "SELECT * FROM projects WHERE id = ? AND faculty_id = ?",
        (project_id, session["user_id"])
    ).fetchone()
    if not project:
        db.close()
        return jsonify({"error": "Project not found"}), 404
    
    required_skills = json.loads(project["required_skills"]) if project["required_skills"] else []
    
    # Get all applications
    applications = db.execute(
        """SELECT a.*, u.name as student_name 
           FROM applications a 
           JOIN users u ON a.student_id = u.id 
           WHERE a.project_id = ? 
           ORDER BY a.match_score DESC""",
        (project_id,)
    ).fetchall()
    
    result = []
    for app in applications:
        student_skills = json.loads(app["student_skills"]) if app["student_skills"] else []
        _, matched, _ = compute_match(student_skills, required_skills)
        
        result.append({
            "student_name": app["student_name"],
            "match_score": app["match_score"],
            "match_reason": app["match_reason"] or "Skill overlap identified, reason unavailable",
            "matched_skills": matched,
            "project_idea": app["project_idea"],
            "interest_statement": app["interest_statement"],
            "status": app["status"],
            "applied_at": app["applied_at"],
            "application_id": app["id"]
        })
    
    db.close()
    return jsonify(result)


# PATCH /faculty/applications/<id>/status
@app.route("/faculty/applications/<int:application_id>/status", methods=["PATCH"])
def update_application_status(application_id):
    if "user_id" not in session or session.get("role") != "teacher":
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    new_status = data.get("status")
    if new_status not in ["accepted", "rejected"]:
        return jsonify({"error": "Invalid status"}), 400
    
    db = get_db()
    
    # Verify application belongs to faculty's project
    app_record = db.execute(
        """SELECT a.*, p.faculty_id 
           FROM applications a 
           JOIN projects p ON a.project_id = p.id 
           WHERE a.id = ?""",
        (application_id,)
    ).fetchone()
    
    if not app_record or app_record["faculty_id"] != session["user_id"]:
        db.close()
        return jsonify({"error": "Application not found"}), 404
    
    db.execute(
        "UPDATE applications SET status = ? WHERE id = ?",
        (new_status, application_id)
    )
    db.commit()
    db.close()
    
    return jsonify({"success": True, "status": new_status})


# ==================== PHASE 5: SMART ANALYTICS ====================

# GET /user/analytics - Returns radar, progress, and match trend data
@app.route("/user/analytics", methods=["GET"])
def get_user_analytics():
    """Get comprehensive analytics data for the user's dashboard."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    user_id = session["user_id"]
    
    # 1. Get progress history for line chart
    history = db.execute("""
        SELECT total_score, skill_breakdown, created_at
        FROM user_analysis_history
        WHERE user_id = ?
        ORDER BY created_at ASC
    """, (user_id,)).fetchall()
    
    # 2. Get latest analysis for radar chart
    latest = db.execute("""
        SELECT total_score, skill_breakdown, matched_skills, missing_skills
        FROM user_analysis_history
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (user_id,)).fetchone()
    
    # 3. Get first analysis for match trend
    first = db.execute("""
        SELECT total_score
        FROM user_analysis_history
        WHERE user_id = ?
        ORDER BY created_at ASC
        LIMIT 1
    """, (user_id,)).fetchone()
    
    # 4. Get session analysis (if available, for fallback)
    session_analysis = session.get("analysis")
    
    db.close()
    
    # Build response
    result = {
        "radar": {},
        "progress": [],
        "match_trend": {}
    }
    
    # Radar chart data (skill breakdown)
    if latest and latest["skill_breakdown"]:
        result["radar"] = json.loads(latest["skill_breakdown"])
    elif session_analysis:
        # Generate from session analysis
        result["radar"] = {
            "frontend": calculate_domain_score(session_analysis.get("matched_skills", []), "frontend"),
            "backend": calculate_domain_score(session_analysis.get("matched_skills", []), "backend"),
            "dsa": calculate_domain_score(session_analysis.get("matched_skills", []), "dsa"),
            "ml": calculate_domain_score(session_analysis.get("matched_skills", []), "ml"),
            "devops": calculate_domain_score(session_analysis.get("matched_skills", []), "devops")
        }
    else:
        result["radar"] = {"frontend": 0, "backend": 0, "dsa": 0, "ml": 0, "devops": 0}
    
    # Progress line chart data
    for h in history:
        result["progress"].append({
            "date": h["created_at"],
            "score": h["total_score"]
        })
    
    # Match trend (before/after)
    if first and latest:
        result["match_trend"] = {
            "before": first["total_score"],
            "after": latest["total_score"],
            "improvement": latest["total_score"] - first["total_score"]
        }
    elif latest:
        result["match_trend"] = {
            "before": 0,
            "after": latest["total_score"],
            "improvement": latest["total_score"]
        }
    elif session_analysis:
        matched = len(session_analysis.get("matched_skills", []))
        result["match_trend"] = {
            "before": 0,
            "after": matched,
            "improvement": matched
        }
    else:
        result["match_trend"] = {"before": 0, "after": 0, "improvement": 0}
    
    # Add stats summary
    if latest:
        result["stats"] = {
            "total_score": latest["total_score"],
            "matched_skills_count": len(json.loads(latest["matched_skills"])) if latest["matched_skills"] else 0,
            "missing_skills_count": len(json.loads(latest["missing_skills"])) if latest["missing_skills"] else 0,
            "analysis_count": len(history)
        }
    elif session_analysis:
        result["stats"] = {
            "total_score": len(session_analysis.get("matched_skills", [])),
            "matched_skills_count": len(session_analysis.get("matched_skills", [])),
            "missing_skills_count": len(session_analysis.get("missing_skills", [])),
            "analysis_count": 0
        }
    else:
        result["stats"] = {
            "total_score": 0,
            "matched_skills_count": 0,
            "missing_skills_count": 0,
            "analysis_count": 0
        }
    
    return jsonify(result)


def calculate_domain_score(skills, domain):
    """Calculate score for a skill domain based on matched skills."""
    domain_keywords = {
        "frontend": ["html", "css", "javascript", "react", "vue", "angular", "typescript", "next.js", "tailwind"],
        "backend": ["python", "flask", "django", "node.js", "express", "sql", "api", "rest"],
        "dsa": ["algorithm", "data structure", "sorting", "searching", "graph", "tree", "dynamic programming"],
        "ml": ["machine learning", "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy", "data science"],
        "devops": ["docker", "kubernetes", "aws", "azure", "ci/cd", "jenkins", "terraform", "git"]
    }
    
    keywords = domain_keywords.get(domain, [])
    matches = sum(1 for skill in skills if any(kw.lower() in skill.lower() for kw in keywords))
    # Scale to 0-100 (max 10 skills = 100%)
    return min(100, int((matches / 10) * 100))


# ==================== PHASE 6: CAREER PATH INTELLIGENCE ====================

# Role skill profiles for career matching
CAREER_ROLES = {
    "Web Developer": {
        "skills": ["html", "css", "javascript", "react", "vue", "angular", "typescript", "next.js", "tailwind", "bootstrap", "jquery"],
        "domains": ["frontend", "backend"],
        "description": "Builds full-stack web applications with modern frameworks"
    },
    "Frontend Engineer": {
        "skills": ["html", "css", "javascript", "react", "vue", "angular", "typescript", "next.js", "tailwind", "sass", "webpack"],
        "domains": ["frontend"],
        "description": "Specializes in user interfaces and client-side experiences"
    },
    "Backend Developer": {
        "skills": ["python", "flask", "django", "node.js", "express", "sql", "postgresql", "mongodb", "redis", "api", "rest", "graphql"],
        "domains": ["backend"],
        "description": "Builds server-side logic, APIs, and database systems"
    },
    "Full Stack Developer": {
        "skills": ["html", "css", "javascript", "react", "node.js", "python", "sql", "mongodb", "express", "django", "api"],
        "domains": ["frontend", "backend"],
        "description": "Handles both frontend and backend development"
    },
    "Data Scientist": {
        "skills": ["python", "pandas", "numpy", "matplotlib", "seaborn", "sql", "statistics", "machine learning", "scikit-learn", "jupyter"],
        "domains": ["ml"],
        "description": "Analyzes data and builds predictive models"
    },
    "ML Engineer": {
        "skills": ["python", "tensorflow", "pytorch", "scikit-learn", "machine learning", "deep learning", "nlp", "computer vision", "mlops"],
        "domains": ["ml"],
        "description": "Deploys and scales machine learning models"
    },
    "DevOps Engineer": {
        "skills": ["docker", "kubernetes", "aws", "azure", "ci/cd", "jenkins", "terraform", "ansible", "linux", "bash", "python"],
        "domains": ["devops"],
        "description": "Manages infrastructure and deployment pipelines"
    },
    "Software Engineer": {
        "skills": ["python", "java", "c++", "javascript", "git", "data structures", "algorithms", "oop", "system design"],
        "domains": ["dsa"],
        "description": "General software development with strong CS fundamentals"
    },
    "Mobile Developer": {
        "skills": ["flutter", "react native", "swift", "kotlin", "android", "ios", "mobile", "firebase"],
        "domains": ["frontend"],
        "description": "Builds native and cross-platform mobile applications"
    },
    "Data Engineer": {
        "skills": ["python", "sql", "spark", "hadoop", "kafka", "airflow", "etl", "data pipelines", "aws", "gcp"],
        "domains": ["backend", "ml"],
        "description": "Designs and maintains data infrastructure and pipelines"
    }
}

def calculate_career_match(user_skills, role_profile):
    """Calculate match score between user skills and role requirements."""
    if not user_skills:
        return 0, []
    
    role_skills = role_profile["skills"]
    
    # Normalize skills to lowercase
    user_set = set(s.lower().strip() for s in user_skills)
    role_set = set(s.lower().strip() for s in role_skills)
    
    # Find overlaps
    exact_matches = user_set & role_set
    
    # Partial matching (if user has "reactjs" and role needs "react")
    partial_matches = set()
    for user_skill in user_set:
        for role_skill in role_set:
            if user_skill in role_skill or role_skill in user_skill:
                partial_matches.add(role_skill)
    
    all_matches = exact_matches | partial_matches
    
    # Calculate weighted score
    if role_skills:
        base_score = (len(all_matches) / len(role_skills)) * 100
        # Bonus for exact matches
        exact_bonus = (len(exact_matches) / len(role_skills)) * 20
        score = min(100, int(base_score + exact_bonus))
    else:
        score = 0
    
    return score, list(all_matches)

def get_top_career_suggestions(user_skills, top_n=3):
    """Get top N career suggestions based on user skills."""
    if not user_skills:
        return []
    
    matches = []
    for role_name, profile in CAREER_ROLES.items():
        score, matched_skills = calculate_career_match(user_skills, profile)
        matches.append({
            "role": role_name,
            "score": score,
            "matched_skills": matched_skills,
            "description": profile["description"],
            "domains": profile["domains"]
        })
    
    # Sort by score descending
    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:top_n]

@app.route("/career/compare", methods=["GET"])
def compare_careers():
    """Compare user's fit across all career roles."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Get user skills from session or database
    db = get_db()
    user_id = session["user_id"]
    
    # Try to get latest analysis from DB
    latest = db.execute("""
        SELECT matched_skills
        FROM user_analysis_history
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (user_id,)).fetchone()
    
    db.close()
    
    # Get skills
    if latest and latest["matched_skills"]:
        user_skills = json.loads(latest["matched_skills"])
    elif session.get("analysis"):
        user_skills = session["analysis"].get("matched_skills", [])
    else:
        user_skills = []
    
    # Calculate match for all roles
    results = []
    for role_name, profile in CAREER_ROLES.items():
        score, matched = calculate_career_match(user_skills, profile)
        results.append({
            "role": role_name,
            "score": score,
            "matched_skills": matched[:5],  # Top 5 matched skills
            "description": profile["description"],
            "domains": profile["domains"]
        })
    
    # Sort by score
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # Get top suggestions
    top_suggestions = results[:3] if len(results) >= 3 else results
    
    return jsonify({
        "all_roles": results,
        "suggested": top_suggestions,
        "best_fit": results[0] if results else None,
        "user_skill_count": len(user_skills)
    })

@app.route("/career/suggest", methods=["POST"])
def get_career_suggestions():
    """Get personalized career suggestions based on current analysis."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    analysis = session.get("analysis")
    if not analysis:
        return jsonify({"error": "Complete skill analysis first"}), 400
    
    user_skills = analysis.get("matched_skills", [])
    suggestions = get_top_career_suggestions(user_skills, top_n=3)
    
    return jsonify({
        "suggestions": suggestions,
        "current_role": analysis.get("role", "Unknown"),
        "current_match": analysis.get("match_score", 0)
    })


# HTML Routes for new pages
@app.route("/faculty/dashboard")
def faculty_dashboard():
    if "user_id" not in session or session.get("role") != "teacher":
        return redirect("/login")
    return render_template("faculty_projects.html")


@app.route("/student/projects-page")
def student_projects_page():
    if "user_id" not in session or session.get("role") != "student":
        return redirect("/login")
    return render_template("student_projects.html")


@app.route("/faculty/applications/<int:project_id>/view")
def faculty_applications_page(project_id):
    if "user_id" not in session or session.get("role") != "teacher":
        return redirect("/login")
    return render_template("faculty_applications.html", project_id=project_id)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
