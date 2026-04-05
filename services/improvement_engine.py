import random

# Simulated Action Database for various skills
ACTIONS_DB = {
    "REST API": [
        {"task": "Build a CRUD REST API using Flask", "time": "2 days", "impact": 15},
        {"task": "Implement JWT Authentication", "time": "1 day", "impact": 10}
    ],
    "React": [
        {"task": "Build a stateful component using Hooks", "time": "1 day", "impact": 10},
        {"task": "Implement React Router in a demo app", "time": "2 days", "impact": 12}
    ],
    "Docker": [
        {"task": "Write a Dockerfile for a Python app", "time": "1 day", "impact": 15},
        {"task": "Set up docker-compose with DB", "time": "2 days", "impact": 20}
    ],
    "Python": [
        {"task": "Solve 5 LeetCode array problems", "time": "2 days", "impact": 5},
        {"task": "Write a web scraper with BeautifulSoup", "time": "1 day", "impact": 10}
    ]
}

def get_next_best_action(missing_skills, focus_role):
    """
    Determine the single most impactful next action for the user.
    """
    if not missing_skills:
        return {
            "task": "Polish your resume and start applying!",
            "time": "1 day",
            "impact": "+5% Confidence",
            "reason": "You meet all core requirements for this role."
        }
    
    # Simple logic: pick the first missing skill and suggest a high-impact task
    target_skill = missing_skills[0]
    
    # Try to find specific tasks, fallback to generic
    tasks = ACTIONS_DB.get(target_skill, [
        {"task": f"Complete a crash course on {target_skill}", "time": "2 days", "impact": 10},
        {"task": f"Build a mini-project focusing on {target_skill}", "time": "3 days", "impact": 15}
    ])
    
    # Pick the one with the highest impact or highest ROI (impact/time)
    # For now, just pick the top one.
    best_action = tasks[0]
    
    return {
        "skill": target_skill,
        "task": best_action["task"],
        "time": best_action["time"],
        "impact": f"+{best_action['impact']}% Score",
        "reason": f"{target_skill} is a critical requirement for a {focus_role}."
    }

def get_improvements_for_skill(skill_name):
    """Get a list of micro-tasks to improve a specific skill."""
    return ACTIONS_DB.get(skill_name, [
        {"task": f"Read documentation on advanced {skill_name} patterns", "time": "4 hours", "impact": 5},
        {"task": f"Build a GitHub repo demonstrating {skill_name}", "time": "2 days", "impact": 12}
    ])
