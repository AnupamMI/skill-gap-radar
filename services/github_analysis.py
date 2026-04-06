import requests
import sqlite3
from collections import defaultdict

def get_db_connection():
    conn = sqlite3.connect("skillgap.db")
    conn.row_factory = sqlite3.Row
    return conn

def analyze_github_profile(username):
    """Fetch user's top languages from GitHub API with robust error handling"""
    try:
        url = f"https://api.github.com/users/{username}/repos?per_page=100"
        response = requests.get(url, timeout=10)

        if response.status_code == 404:
            print(f"GitHub user not found: {username}")
            return []
        
        if response.status_code == 403:
            print(f"GitHub API Rate limit exceeded.")
            return []

        if response.status_code != 200:
            print(f"GitHub API error: {response.status_code}")
            return []

        repos = response.json()
        if not isinstance(repos, list):
            return []

        language_count = defaultdict(int)
        detected_frameworks = set()
        total_complexity = 0
        
        FRAMEWORK_KEYWORDS = ['react', 'flask', 'django', 'node', 'express', 'next', 'spring', 'pytorch', 'tensorflow', 'pandas']
        
        for repo in repos:
            lang = repo.get("language")
            if lang:
                language_count[lang.lower()] += 1
                
            # Complexity heuristics: size, has_wiki, stargazers
            size = repo.get("size", 0)
            stars = repo.get("stargazers_count", 0)
            has_wiki = repo.get("has_wiki", False)
            
            complexity_score = 0
            if size > 1000: complexity_score += 1
            if size > 10000: complexity_score += 2
            if stars > 0: complexity_score += 1
            if has_wiki: complexity_score += 1
            total_complexity += complexity_score
            
            # Framework detection from description or topics
            desc = (repo.get("description") or "").lower()
            topics = repo.get("topics", [])
            combined_text = desc + " " + " ".join(topics)
            
            for fw in FRAMEWORK_KEYWORDS:
                if fw in combined_text:
                    detected_frameworks.add(fw)

        langs = list(language_count.keys())
        
        # Assess overall quality/depth
        avg_complexity = total_complexity / max(1, len(repos))
        depth = "Beginner"
        if avg_complexity >= 2: depth = "Intermediate"
        if avg_complexity >= 4: depth = "Advanced"

        return {
            "languages": langs,
            "frameworks": list(detected_frameworks),
            "depth": depth
        }
    except Exception as e:
        print(f"CRITICAL ERROR in GitHub Analysis: {e}")
        return []
def verify_github_skills(user_id, github_username):
    """Verify skills based on GitHub languages and update user_skills table"""
    github_data = analyze_github_profile(github_username)
    if not github_data or not github_data.get("languages"):
        return {"verified_ids": [], "depth": "Beginner", "frameworks": []}

    github_langs = github_data["languages"]
    conn = get_db_connection()
    db_skills = conn.execute("SELECT id, name FROM skills").fetchall()
    
    skill_map = {s['name'].lower(): s['id'] for s in db_skills}
    
    verified_ids = []
    for lang in github_langs:
        # Simple mapping for now
        if lang in skill_map:
            verified_ids.append(skill_map[lang])
        # Handle some common mappings if they don't match exactly
        elif lang == 'jupyter notebook' and 'python' in skill_map:
            verified_ids.append(skill_map['python'])
            
    # Also map framework keywords to skills (e.g., 'react' -> React id)
    for fw in github_data["frameworks"]:
        if fw in skill_map:
            verified_ids.append(skill_map[fw])

    # Save to user_skills as 'github' source
    for sid in verified_ids:
        cur = conn.execute("SELECT id, source FROM user_skills WHERE user_id=? AND skill_id=?", (user_id, sid))
        row = cur.fetchone()
        if not row:
            conn.execute("INSERT INTO user_skills(user_id, skill_id, score, source) VALUES(?,?,?,?)",
                         (user_id, sid, 1.0, 'github'))
        elif row['source'] == 'resume':
            # Upgrade source to github if it was only resume
            conn.execute("UPDATE user_skills SET source='github' WHERE id=?", (row['id'],))

    conn.commit()
    conn.close()
    
    return {
        "verified_ids": verified_ids,
        "depth": github_data["depth"],
        "frameworks": github_data["frameworks"]
    }
