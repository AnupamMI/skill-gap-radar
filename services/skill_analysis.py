import sqlite3
import spacy
from pdfminer.high_level import extract_text
from spacy.matcher import PhraseMatcher
import os
from .improvement_engine import get_next_best_action, get_improvements_for_skill

nlp = spacy.load("en_core_web_sm")

def get_db_connection():
    conn = sqlite3.connect("skillgap.db")
    conn.row_factory = sqlite3.Row
    return conn

def extract_skills_from_pdf(pdf_path):
    """Extract skills from a resume PDF using Spacy PhraseMatcher"""
    try:
        if not os.path.exists(pdf_path):
            print(f"File not found: {pdf_path}")
            return []

        conn = get_db_connection()
        db_skills = conn.execute("SELECT id, name FROM skills").fetchall()
        conn.close()

        if not db_skills:
            print("No skills found in database to match against.")
            return []

        skill_map = {s['name'].lower(): s['id'] for s in db_skills}
        
        # Build matcher
        matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
        patterns = [nlp.make_doc(name) for name in skill_map.keys()]
        matcher.add("SKILLS", patterns)

        # Extract and clean text
        text = extract_text(pdf_path)
        if not text:
            print("PDF extraction returned empty text.")
            return []

        # Cleanup whitespace and normalize
        text = " ".join(text.split())
        doc = nlp(text)
        matches = matcher(doc)

        found_skill_ids = set()
        for match_id, start, end in matches:
            span = doc[start:end]
            skill_id = skill_map.get(span.text.lower().strip())
            if skill_id:
                found_skill_ids.add(skill_id)
        
        print(f"Extracted {len(found_skill_ids)} skills from {pdf_path}")
        return list(found_skill_ids)

    except Exception as e:
        print(f"CRITICAL ERROR in extract_skills: {e}")
        return []

def calculate_skill_gap(user_id, goal_role):
    """
    Compare user's current skills vs target role requirements.
    In a real app, ROLE_REQUIREMENTS would be in the DB.
    """
    ROLE_REQUIREMENTS = {
        "Web Developer": ["HTML", "CSS", "JavaScript", "React", "Node.js", "SQL", "Git"],
        "Data Scientist": ["Python", "Pandas", "SQL", "Machine Learning", "Git", "NumPy", "Matplotlib"],
        "Backend Developer": ["Python", "Flask", "SQL", "Docker", "Git", "Node.js", "Redis"],
        "ML Engineer": ["Python", "PyTorch", "TensorFlow", "Scikit-Learn", "Git", "Docker", "Math"],
        "Frontend Engineer": ["HTML", "CSS", "TypeScript", "React", "Next.js", "Git", "Tailwind"],
        "DevOps Engineer": ["Docker", "Kubernetes", "AWS", "Git", "Linux", "Terraform", "CI/CD"]
    }

    required_skill_names = ROLE_REQUIREMENTS.get(goal_role, [])
    if not required_skill_names:
        return None

    conn = get_db_connection()
    
    # Get user's current skills (resume + github)
    user_skills = conn.execute("""
        SELECT s.name, us.score, us.source 
        FROM user_skills us
        JOIN skills s ON s.id = us.skill_id
        WHERE us.user_id = ?
    """, (user_id,)).fetchall()
    
    user_skill_names = {s['name'].lower() for s in user_skills}
    
    strong = []
    moderate = []
    missing = []
    
    for req in required_skill_names:
        req_lower = req.lower()
        if req_lower in user_skill_names:
            sources = [s['source'] for s in user_skills if s['name'].lower() == req_lower]
            if 'github' in sources:
                strong.append({
                    "name": req,
                    "score": 100,
                    "confidence": "High",
                    "evidence": ["Verified in GitHub Projects", "Found in Resume"] if 'resume' in sources else ["Verified in GitHub Projects"],
                    "missing" : [],
                    "improvements": []
                })
            else:
                moderate.append({
                    "name": req,
                    "score": 60,
                    "confidence": "Medium",
                    "evidence": ["Found in Resume"],
                    "missing" : ["Practical implementation verification"],
                    "improvements": get_improvements_for_skill(req)
                })
        else:
            missing.append({
                "name": req,
                "score": 20,
                "confidence": "Low",
                "evidence": ["None found"],
                "missing" : ["Core concepts", "Practical experience"],
                "improvements": get_improvements_for_skill(req)
            })

    # Calculate match percentage
    total = len(required_skill_names)
    match_pct = round(((len(strong) + (len(moderate) * 0.5)) / total) * 100) if total > 0 else 0

    # Next Best Action
    missing_names = [m["name"] for m in missing]
    next_action = get_next_best_action(missing_names, goal_role)

    conn.close()
    
    return {
        "strong": strong,
        "moderate": moderate,
        "missing": missing,
        "match_percentage": match_pct,
        "gap_score": 100 - match_pct,
        "next_action": next_action
    }

def save_user_skills(user_id, skill_ids, source='resume'):
    """Save extracted skills to user_skills table"""
    conn = get_db_connection()
    for sid in skill_ids:
        cur = conn.execute("SELECT id FROM user_skills WHERE user_id=? AND skill_id=?", (user_id, sid))
        if not cur.fetchone():
            conn.execute("INSERT INTO user_skills(user_id, skill_id, score, source) VALUES(?,?,?,?)", 
                         (user_id, sid, 1.0, source))
    conn.commit()
    conn.close()
