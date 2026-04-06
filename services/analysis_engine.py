"""
Core analysis engine: resume text extraction + GitHub validation.
Produces a structured result dict stored in session['analysis'].
No DB dependency for the analysis itself.
"""

import re
from collections import defaultdict

# ── 1.  Full role skill config (with confidence tiers) ──────────────────────
ROLES_CONFIG = {
    "Web Developer": {
        "required": ["html", "css", "javascript", "react", "git", "sql", "api design"],
        "bonus":    ["typescript", "node.js", "tailwind", "next.js", "testing"]
    },
    "Backend Developer": {
        "required": ["python", "sql", "rest apis", "git", "docker"],
        "bonus":    ["flask", "django", "redis", "postgresql", "linux", "celery"]
    },
    "Data Scientist": {
        "required": ["python", "pandas", "numpy", "sql", "statistics", "machine learning"],
        "bonus":    ["matplotlib", "scikit-learn", "jupyter", "tensorflow", "spark"]
    },
    "ML Engineer": {
        "required": ["python", "machine learning", "scikit-learn", "docker", "git"],
        "bonus":    ["pytorch", "tensorflow", "cuda", "fastapi", "linux", "mlops"]
    },
}

# Aliases: maps resume text tokens → canonical skill names in ROLES_CONFIG
ALIASES = {
    "react.js": "react",
    "reactjs": "react",
    "nodejs": "node.js",
    "node": "node.js",
    "postgres": "postgresql",
    "postgre": "postgresql",
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "machine learning": "machine learning",
    "ml": "machine learning",
    "api": "api design",
    "rest api": "rest apis",
    "restful": "rest apis",
    "numpy": "numpy",
    "pandas": "pandas",
    "tensorflow": "tensorflow",
    "tf": "tensorflow",
    "pytorch": "pytorch",
    "torch": "pytorch",
    "statistics": "statistics",
    "statistical": "statistics",
    "deep learning": "machine learning",
    "neural network": "machine learning",
    "flask": "flask",
    "django": "django",
    "tailwindcss": "tailwind",
    "tailwind css": "tailwind",
}

# GitHub language → canonical skill mapping
GITHUB_LANG_MAP = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "html": "html",
    "css": "css",
    "jupyter notebook": "python",
    "sql": "sql",
}

GITHUB_TOPIC_MAP = {
    "react": "react",
    "nextjs": "next.js",
    "next-js": "next.js",
    "flask": "flask",
    "django": "django",
    "pytorch": "pytorch",
    "tensorflow": "tensorflow",
    "docker": "docker",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "pandas": "pandas",
    "numpy": "numpy",
    "machine-learning": "machine learning",
    "ml": "machine learning",
    "redis": "redis",
    "postgresql": "postgresql",
    "tailwind": "tailwind",
    "node": "node.js",
    "fastapi": "fastapi",
    "linux": "linux",
    "cuda": "cuda",
}


def _normalize(text: str) -> str:
    """Lower-case and collapse whitespace."""
    return re.sub(r"\s+", " ", text.lower().strip())


def extract_skills_from_text(raw_text: str, goal_role: str) -> dict:
    """
    Match resume text against ROLES_CONFIG using keyword + alias scanning.
    Returns a structured dict ready for session storage.
    """
    if goal_role not in ROLES_CONFIG:
        goal_role = "Web Developer"

    role_cfg = ROLES_CONFIG[goal_role]
    all_required = role_cfg["required"]
    all_bonus    = role_cfg["bonus"]
    all_skills   = list(dict.fromkeys(all_required + all_bonus))  # ordered, no dupes

    text = _normalize(raw_text)

    matched = {}
    for skill in all_skills:
        # Try exact skill name
        canonical = ALIASES.get(skill, skill)
        # Check the skill itself and its aliases in the text
        found = (skill in text) or (canonical in text)
        if not found:
            # Check each alias that maps to this canonical skill
            for alias, target in ALIASES.items():
                if target == skill and alias in text:
                    found = True
                    break
        if found:
            tier = "required" if skill in all_required else "bonus"
            confidence = 0.9 if tier == "required" else 0.75
            matched[skill] = {"confidence": confidence, "source": "resume", "tier": tier}

    matched_names  = list(matched.keys())
    missing_req    = [s for s in all_required if s not in matched_names]
    missing_bonus  = [s for s in all_bonus   if s not in matched_names]

    # Score: required skills weighted 70%, bonus 30%
    req_score = (
        sum(1 for s in all_required if s in matched_names) / len(all_required)
    ) if all_required else 0
    bon_score = (
        sum(1 for s in all_bonus if s in matched_names) / len(all_bonus)
    ) if all_bonus else 0
    match_score = round((req_score * 0.7 + bon_score * 0.3) * 100, 1)

    return {
        "role": goal_role,
        "matched": matched,       # {skill: {confidence, source, tier}}
        "missing_required": missing_req,
        "missing_bonus":    missing_bonus,
        "match_score":      match_score,
        # Flat lists kept for backward compat with dashboard / AI mentor
        "matched_skills":  matched_names,
        "missing_skills":  missing_req + missing_bonus,
    }


def enrich_with_github(analysis: dict, github_username: str) -> dict:
    """
    Fetch GitHub profile and upgrade matched skills confidence
    (or add new ones) based on languages + repo topics.
    Mutates and returns the analysis dict.
    """
    if not github_username or not github_username.strip():
        return analysis

    try:
        import urllib.request, json
        url = f"https://api.github.com/users/{github_username}/repos?per_page=100&sort=updated"
        req = urllib.request.Request(url, headers={"User-Agent": "SkillGapRadar/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            repos = json.loads(resp.read())
        if not isinstance(repos, list):
            return analysis
    except Exception as e:
        print(f"GitHub fetch error: {e}")
        return analysis

    # Collect languages
    lang_count = defaultdict(int)
    topic_set  = set()
    for repo in repos:
        lang = (repo.get("language") or "").lower()
        if lang:
            lang_count[lang] += 1
        for t in repo.get("topics", []):
            topic_set.add(t.lower())

    github_skills = set()
    for lang, _ in lang_count.items():
        mapped = GITHUB_LANG_MAP.get(lang)
        if mapped:
            github_skills.add(mapped)
    for topic in topic_set:
        mapped = GITHUB_TOPIC_MAP.get(topic)
        if mapped:
            github_skills.add(mapped)

    # Upgrade or add
    for skill in github_skills:
        if skill in analysis["matched"]:
            analysis["matched"][skill]["confidence"] = 1.0
            if analysis["matched"][skill]["source"] == "resume":
                analysis["matched"][skill]["source"] = "resume+github"
        else:
            # Check if this skill is relevant to the role
            all_role_skills = (
                ROLES_CONFIG.get(analysis["role"], {}).get("required", []) +
                ROLES_CONFIG.get(analysis["role"], {}).get("bonus", [])
            )
            if skill in all_role_skills:
                tier = "required" if skill in ROLES_CONFIG[analysis["role"]]["required"] else "bonus"
                analysis["matched"][skill] = {
                    "confidence": 1.0,
                    "source": "github",
                    "tier": tier
                }
                # Remove from missing lists
                analysis["missing_required"] = [s for s in analysis["missing_required"] if s != skill]
                analysis["missing_bonus"]    = [s for s in analysis["missing_bonus"]    if s != skill]

    # Recalculate flat lists + score
    matched_names = list(analysis["matched"].keys())
    analysis["matched_skills"] = matched_names
    analysis["missing_skills"]  = analysis["missing_required"] + analysis["missing_bonus"]
    analysis["github_username"] = github_username

    all_required = ROLES_CONFIG[analysis["role"]]["required"]
    all_bonus    = ROLES_CONFIG[analysis["role"]]["bonus"]
    req_score = sum(1 for s in all_required if s in matched_names) / max(len(all_required), 1)
    bon_score = sum(1 for s in all_bonus    if s in matched_names) / max(len(all_bonus),    1)
    analysis["match_score"] = round((req_score * 0.7 + bon_score * 0.3) * 100, 1)

    return analysis


def build_roadmap(analysis: dict) -> dict:
    """
    Build a structured, phase-ordered learning roadmap from the gap analysis.
    Returns a roadmap dict stored inside session['analysis']['roadmap'].
    """
    role            = analysis.get("role", "Engineer")
    missing_req     = analysis.get("missing_required", [])
    missing_bonus   = analysis.get("missing_bonus", [])
    matched         = analysis.get("matched", {})

    # Phase 1 – Foundations: top 3 critical missing required skills
    phase1 = []
    for skill in missing_req[:3]:
        phase1.append({
            "skill": skill,
            "action": f"Learn core concepts of {skill}",
            "outcome": f"Understand fundamentals and build a small demo with {skill}",
            "priority": "critical",
        })

    # Phase 2 – Build: remaining missing required + first 2 bonus
    phase2 = []
    for skill in missing_req[3:]:
        phase2.append({
            "skill": skill,
            "action": f"Build a project using {skill}",
            "outcome": f"Integrate {skill} into a real-world project",
            "priority": "high",
        })
    for skill in missing_bonus[:2]:
        phase2.append({
            "skill": skill,
            "action": f"Learn and practice {skill}",
            "outcome": f"Add {skill} to your portfolio project",
            "priority": "medium",
        })

    # Phase 3 – Polish: remaining bonus + skills that need GitHub validation
    phase3 = []
    resume_only = [s for s, v in matched.items() if v["source"] == "resume"]
    for skill in resume_only[:3]:
        phase3.append({
            "skill": skill,
            "action": f"Push a {skill} project to GitHub",
            "outcome": f"Validate {skill} knowledge with public code",
            "priority": "medium",
        })
    for skill in missing_bonus[2:]:
        phase3.append({
            "skill": skill,
            "action": f"Explore advanced {skill} patterns",
            "outcome": f"Demonstrate {skill} in a production-style codebase",
            "priority": "low",
        })

    # Phase 4 – Always fixed: career readiness
    phase4 = [{
        "skill": "Career Readiness",
        "action": "Polish resume, GitHub profile, and practice mock interviews",
        "outcome": f"Apply confidently for {role} positions",
        "priority": "final",
    }]

    return {
        "role":   role,
        "phases": {
            "Phase 1 – Foundations":   phase1,
            "Phase 2 – Build":         phase2,
            "Phase 3 – Polish":        phase3,
            "Phase 4 – Career Ready":  phase4,
        }
    }
