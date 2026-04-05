import sqlite3

def get_db_connection():
    conn = sqlite3.connect("skillgap.db")
    conn.row_factory = sqlite3.Row
    return conn

def record_skill_history(user_id, skill_id, score):
    """Record a point in time score for a skill."""
    conn = get_db_connection()
    
    # Check if we already recorded a score today to avoid spam, or just insert
    # For MVP, we just insert every time it's re-evaluated or updated.
    conn.execute("""
        INSERT INTO skill_history(user_id, skill_id, score) 
        VALUES(?,?,?)
    """, (user_id, skill_id, score))
    
    conn.commit()
    conn.close()

def get_growth_indicators(user_id):
    """
    Calculate growth (Before vs After) for skills.
    Looks at the oldest record vs the newest record.
    """
    conn = get_db_connection()
    
    # Get distinct skills user has history for
    skills = conn.execute("""
        SELECT DISTINCT h.skill_id, s.name 
        FROM skill_history h
        JOIN skills s ON s.id = h.skill_id
        WHERE h.user_id = ?
    """, (user_id,)).fetchall()
    
    growth_data = []
    
    for s in skills:
        skill_id = s['skill_id']
        name = s['name']
        
        # Get oldest
        oldest = conn.execute("""
            SELECT score FROM skill_history 
            WHERE user_id = ? AND skill_id = ? 
            ORDER BY timestamp ASC LIMIT 1
        """, (user_id, skill_id)).fetchone()
        
        # Get newest (current)
        newest = conn.execute("""
            SELECT score FROM skill_history 
            WHERE user_id = ? AND skill_id = ? 
            ORDER BY timestamp DESC LIMIT 1
        """, (user_id, skill_id)).fetchone()
        
        if oldest and newest:
            diff = newest['score'] - oldest['score']
            if diff > 0:
                growth_data.append({
                    "skill": name,
                    "old_score": oldest['score'],
                    "new_score": newest['score'],
                    "growth": f"+{diff}%"
                })
                
    conn.close()
    return growth_data
