import sys
role = sys.argv[1].strip().lower()


ROLE_SKILLS = {
    "web developer": ["html","css","javascript","react","node","sql","git"],
    "data scientist": ["python","numpy","pandas","machine learning","matplotlib","sql"],
    "backend developer": ["python","java","sql","api","docker","git"]
}

# auto match similar text
for key in ROLE_SKILLS:
    if role in key:
        role = key
        break

if role not in ROLE_SKILLS:
    print("Available roles:", ", ".join(ROLE_SKILLS.keys()))
    exit()


# load github verified skills
with open("verified_skills.txt","r") as f:
    github_skills = [line.strip().lower() for line in f]

# load resume detected skills
with open("resume_skills.txt","r") as f:
    resume_skills = [line.strip().lower() for line in f]

required = ROLE_SKILLS[role]

strong = []
moderate = []
missing = []

for skill in required:
    if skill in github_skills:
        strong.append(skill)
    elif skill in resume_skills:
        moderate.append(skill)
    else:
        missing.append(skill)

print("\n===== RESULT =====\n")

print("Strong Skills (verified by projects):")
for s in strong:
    print("-", s)

print("\nModerate Skills (resume only):")
for s in moderate:
    print("-", s)

print("\nMissing Skills:")
for s in missing:
    print("-", s)

print("\nRecommendation:")
for s in missing:
    print(f"Learn {s} and build a project using it")
