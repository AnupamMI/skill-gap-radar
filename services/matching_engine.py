import sqlite3

def get_db_connection():
    conn = sqlite3.connect("skillgap.db")
    conn.row_factory = sqlite3.Row
    return conn

def match_student_with_teachers(user_id):
    """Suggest teachers based on student skill gaps and teacher expertise"""
    conn = get_db_connection()
    
    # Get student's gaps (for simplicity, we track last request)
    request = conn.execute("""
        SELECT goal_role FROM mentorship_requests 
        WHERE student_id = ? ORDER BY created_at DESC LIMIT 1
    """, (user_id,)).fetchone()
    
    if not request:
        return []

    goal_role = request['goal_role']
    
    # Find teachers who match this role or have expertise in missing skills
    # Since we don't have a formal "expertise" table for teachers yet, 
    # we'll use their bio or a simple role mapping.
    
    teachers = conn.execute("""
        SELECT id, name, bio, role FROM users WHERE role = 'teacher'
    """).fetchall()

    matches = []
    for t in teachers:
        # Simple string matching on bio
        match_score = 0
        reason = "Matches your career interest."
        
        bio = (t['bio'] or "").lower()
        if goal_role.lower() in bio:
            match_score += 40
            reason = f"Specialist in {goal_role}."
        
        # Check if teacher mentions some of the missing skills
        # (This is simulated for now as we don't have a teacher skill table yet)
        if "backend" in bio and goal_role == "Web Developer":
            match_score += 15
            reason = "Can help bridge your backend gap."

        if match_score == 0:
            match_score = 25
            
        matches.append({
            "id": t['id'],
            "name": t['name'],
            "bio": t['bio'],
            "match_score": match_score,
            "reason": reason
        })

    # Sort by match score
    matches = sorted(matches, key=lambda x: x['match_score'], reverse=True)
    
    conn.close()
    return matches[:3] # Top 3 matches
