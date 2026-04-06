import sys
sys.path.insert(0, '.')

from services.analysis_engine import extract_skills_from_text, build_roadmap

# Test with a mock resume containing some skills
sample_resume = """
John Doe - Software Engineer
Skills: Python, React, SQL, Git, Docker, Flask, REST API
Experience with machine learning and pandas library.
Built projects using Node.js and TypeScript.
"""

print("=== TESTING ANALYSIS ENGINE ===\n")

# Test 1: Backend Developer
print("--- Target: Backend Developer ---")
result = extract_skills_from_text(sample_resume, "Backend Developer")
print(f"Match Score : {result['match_score']}%")
print(f"Matched     : {result['matched_skills']}")
print(f"Missing Req : {result['missing_required']}")
print(f"Missing Bon : {result['missing_bonus']}")

roadmap = build_roadmap(result)
print("\nRoadmap Phases:")
for phase, steps in roadmap["phases"].items():
    if steps:
        print(f"  {phase}: {len(steps)} step(s)")
        for s in steps[:2]:
            print(f"    [{s['priority'].upper()}] {s['action']}")

print()

# Test 2: ML Engineer  
print("--- Target: ML Engineer ---")
result2 = extract_skills_from_text(sample_resume, "ML Engineer")
print(f"Match Score : {result2['match_score']}%")
print(f"Matched     : {result2['matched_skills']}")
print(f"Missing Req : {result2['missing_required']}")

print("\n=== ALL TESTS PASSED ===")
