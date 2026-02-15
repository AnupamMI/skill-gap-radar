import sys
pdf_path = sys.argv[1]   # get file from website

import spacy
from pdfminer.high_level import extract_text
from spacy.matcher import PhraseMatcher


nlp = spacy.load("en_core_web_sm")


with open("skills_cleaned.txt", "r", encoding="utf-8") as f:
    skills = [line.strip().lower() for line in f if len(line.strip()) > 2]

print("Total skills in DB:", len(skills))

# Build matcher
matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
patterns = [nlp.make_doc(skill) for skill in skills]
matcher.add("SKILLS", patterns)

print("Reading resume...")
text = extract_text(pdf_path)
doc = nlp(text)

matches = matcher(doc)

# Collect matched skills
found_skills = set()
for match_id, start, end in matches:
    span = doc[start:end]
    found_skills.add(span.text.lower())

print("\n===== DETECTED SKILLS =====\n")

# Remove useless phrases
cleaned = []
for skill in found_skills:
    if len(skill) < 3:
        continue
    if skill in ["skills","technical skills","soft skills","languages"]:
        continue
    cleaned.append(skill)

# Known technical keywords (whitelist)
TECH_KEYWORDS = [
    "python","java","c++","c","javascript","html","css","react","node",
    "sql","mysql","mongodb","git","github","linux","flask","django",
    "machine learning","deep learning","data analysis","pandas","numpy",
    "opencv","tensorflow","web development"
]

# Keep only real technical skills
final_skills = []
for skill in cleaned:
    for tech in TECH_KEYWORDS:
        if tech in skill:
            final_skills.append(tech)

final_skills = sorted(set(final_skills))

# Print final result
for s in final_skills:
    print("-", s)
    
# Save final skills to a file
with open("resume_skills.txt", "w") as f:
    for s in final_skills:
        f.write(s + "\n")
