import sqlite3

def get_db_connection():
    conn = sqlite3.connect("skillgap.db")
    conn.row_factory = sqlite3.Row
    return conn

def generate_roadmap(user_id, target_role, missing_skills, moderate_skills):
    """
    Generate a 4-phase structured roadmap based on skill gaps.
    Saves it to the DB and returns the roadmap object.
    """
    conn = get_db_connection()
    
    # 1. Create Roadmap entry
    cur = conn.execute("INSERT INTO roadmaps(user_id, target_role) VALUES(?,?)", (user_id, target_role))
    roadmap_id = cur.lastrowid
    
    steps = []
    
    # Phase 1: Foundations (Targeting core missing skills)
    if missing_skills:
        foundations = missing_skills[:2] # Take top 2 missing
        for skill in foundations:
            steps.append(("Phase 1: Foundations", f"Learn core concepts of {skill}", f"Basic syntax, data structures, and simple scripts in {skill}.", "3 days"))
    else:
        steps.append(("Phase 1: Foundations", "Review Fundamentals", "Quick brush-up on basic concepts.", "1 day"))

    # Phase 2: Intermediate (Targeting moderate skills or remaining missing)
    if moderate_skills:
        interm = moderate_skills[:2]
        for skill in interm:
            steps.append(("Phase 2: Intermediate", f"Build a project using {skill}", f"Apply {skill} in a real-world scenario (e.g., API, Web App).", "1 week"))
    else:
        steps.append(("Phase 2: Intermediate", "Build a Multi-Component Project", "Combine multiple skills into a cohesive project.", "1 week"))

    # Phase 3: Advanced
    steps.append(("Phase 3: Advanced", "Architecture & Best Practices", f"Learn design patterns and write unit tests for your {target_role} projects.", "2 weeks"))
    
    # Phase 4: Industry Readiness
    steps.append(("Phase 4: Industry Readiness", "Resume & Interview Prep", "Push projects to GitHub, write READMEs, and practice mock interviews.", "Ongoing"))
    
    # Insert steps into DB
    db_steps = []
    for phase, title, desc, time in steps:
        cur = conn.execute("""
            INSERT INTO roadmap_steps(roadmap_id, phase, title, description, resources)
            VALUES(?,?,?,?,?)
        """, (roadmap_id, phase, title, desc, f"Time: {time}"))
        db_steps.append({
            "id": cur.lastrowid,
            "phase": phase,
            "title": title,
            "description": desc,
            "time": time,
            "status": "pending"
        })
        
    conn.commit()
    conn.close()
    
    return {
        "roadmap_id": roadmap_id,
        "target_role": target_role,
        "steps": db_steps
    }

def get_user_roadmap(user_id):
    """Fetch the latest active roadmap for a user."""
    conn = get_db_connection()
    
    roadmap = conn.execute("""
        SELECT id, target_role FROM roadmaps 
        WHERE user_id = ? ORDER BY created_at DESC LIMIT 1
    """, (user_id,)).fetchone()
    
    if not roadmap:
        conn.close()
        return None
        
    steps = conn.execute("""
        SELECT id, phase, title, description, resources, status
        FROM roadmap_steps WHERE roadmap_id = ?
    """, (roadmap['id'],)).fetchall()
    
    conn.close()
    
    # Group by phase for easy UI rendering
    phases = {}
    for step in steps:
        phase_name = step['phase'].split(':')[0].strip() # e.g. "Phase 1"
        if phase_name not in phases:
            phases[phase_name] = []
        phases[phase_name].append(dict(step))
        
    return {
        "roadmap_id": roadmap['id'],
        "target_role": roadmap['target_role'],
        "phases": phases
    }

def update_step_status(step_id, status):
    conn = get_db_connection()
    conn.execute("UPDATE roadmap_steps SET status = ? WHERE id = ?", (status, step_id))
    conn.commit()
    conn.close()
