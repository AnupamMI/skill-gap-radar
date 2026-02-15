import sys
username = sys.argv[1]

import requests
from collections import defaultdict
from datetime import datetime



url = f"https://api.github.com/users/{username}/repos?per_page=100"
response = requests.get(url)

if response.status_code != 200:
    print("User not found or API error")
    exit()

repos = response.json()

language_count = defaultdict(int)
recent_usage = defaultdict(int)
repo_sizes = defaultdict(int)

current_year = datetime.now().year


for repo in repos:

    lang = repo["language"]
    if not lang:
        continue

    lang = lang.lower()

    language_count[lang] += 1
    repo_sizes[lang] += repo["size"]

    updated_year = int(repo["updated_at"][:4])
    if current_year - updated_year <= 1:
        recent_usage[lang] += 1

repo_count = max(len(repos), 1)


verified = []

for lang in language_count:

    repo_score = language_count[lang] / repo_count
    activity_score = min(repo_sizes[lang] / 20000, 1)
    recency_score = recent_usage[lang] / language_count[lang]

    confidence = round((repo_score*0.4 + activity_score*0.4 + recency_score*0.2), 2)

    if confidence >= 0.4:   # moderate or strong = verified
        verified.append(lang)
        level = "Verified"
    else:
        level = "Weak"

print(f"{lang.upper():12} Score: {confidence} -> {level}")

# save verified skills
with open("verified_skills.txt", "w") as f:
    for skill in verified:
        f.write(skill + "\n")

print("\nVerified skills saved to verified_skills.txt")
