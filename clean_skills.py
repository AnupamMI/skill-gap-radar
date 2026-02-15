print("Cleaning skills database...")

valid_skills = []

with open("skills_db.txt", "r", encoding="utf-8", errors="ignore") as f:
    original = f.readlines()

for skill in original:
    skill = skill.strip().lower()

    # remove tiny or useless tokens
    if len(skill) < 3:
        continue
    if skill.isnumeric():
        continue
    if skill in ["a","an","the","and","or","on","in","of"]:
        continue
    if skill.endswith(".") or skill.endswith(","):
        continue

    valid_skills.append(skill)

# remove duplicates
valid_skills = sorted(set(valid_skills))

with open("skills_cleaned.txt", "w", encoding="utf-8") as f:
    for s in valid_skills:
        f.write(s + "\n")

print("Original skills:", len(original))
print("Clean skills:", len(valid_skills))
print("skills_cleaned.txt created!")
