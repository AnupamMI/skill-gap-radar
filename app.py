from flask import Flask, render_template, request
import subprocess
import os

app = Flask(__name__)
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/full_analysis", methods=["POST"])
def full_analysis():

    # -------- Save Resume --------
    file = request.files["resume"]
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    # -------- Resume --------
    resume_raw = subprocess.getoutput(f'python analyze_resume.py "{filepath}"')
    resume_skills = [
        line.strip("- ").strip()
        for line in resume_raw.split("\n")
        if line.startswith("-")
    ]

    # -------- GitHub --------
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

    strong = []
    moderate = []
    missing = []

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

    # -------- Skill Score Meter --------
    skill_scores = {}

    for s in strong:
        skill_scores[s] = 90
    for s in moderate:
        skill_scores[s] = 60
    for s in missing:
        skill_scores[s] = 20

    # -------- Project Recommendation Engine --------
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

    recommendations = []
    for skill in missing:
        if skill in PROJECT_MAP:
            recommendations.append(PROJECT_MAP[skill])
        else:
            recommendations.append(f"Build a project using {skill}")

    return render_template(
        "dashboard.html",
        resume=resume_skills,
        verified=verified_skills,
        strong=strong,
        moderate=moderate,
        missing=missing,
        scores=skill_scores,
        projects=recommendations
    )


if __name__ == "__main__":
    app.run(debug=True)
