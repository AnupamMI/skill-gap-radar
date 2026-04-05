import sqlite3
import os

DB = "skillgap.db"

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # USERS: student/teacher roles, bio, github_username, avatar
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT,
        bio TEXT,
        github_username TEXT,
        avatar TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # SKILLS: predefined skill list with categories/weights
    cur.execute("""
    CREATE TABLE IF NOT EXISTS skills(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        category TEXT,
        weight INTEGER DEFAULT 1
    )
    """)

    # USER_SKILLS: current skill scores
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_skills(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        skill_id INTEGER,
        score REAL,
        source TEXT, -- 'resume', 'github', 'manual'
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, skill_id),
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(skill_id) REFERENCES skills(id)
    )
    """)

    # SKILL_HISTORY: track score progress over time
    cur.execute("""
    CREATE TABLE IF NOT EXISTS skill_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        skill_id INTEGER,
        score REAL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(skill_id) REFERENCES skills(id)
    )
    """)

    # ROADMAPS: career path roadmaps
    cur.execute("""
    CREATE TABLE IF NOT EXISTS roadmaps(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        target_role TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # ROADMAP_STEPS: individual tasks in a roadmap
    cur.execute("""
    CREATE TABLE IF NOT EXISTS roadmap_steps(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roadmap_id INTEGER,
        phase TEXT, -- 'Foundations', 'Intermediate', 'Advanced', 'Industry'
        title TEXT,
        description TEXT,
        resources TEXT,
        status TEXT DEFAULT 'pending', -- 'pending', 'completed'
        FOREIGN KEY(roadmap_id) REFERENCES roadmaps(id)
    )
    """)

    # MENTORSHIP_REQUESTS: student goals, project ideas
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mentorship_requests(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        goal_role TEXT,
        project_idea TEXT,
        status TEXT DEFAULT 'pending', -- 'pending', 'matched', 'completed'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(student_id) REFERENCES users(id)
    )
    """)

    # MENTORSHIP_GROUPS: teacher-led groups
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mentorship_groups(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER,
        name TEXT,
        description TEXT,
        capacity INTEGER DEFAULT 5,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(teacher_id) REFERENCES users(id)
    )
    """)

    # GROUP_MEMBERS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS group_members(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER,
        student_id INTEGER,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(group_id) REFERENCES mentorship_groups(id),
        FOREIGN KEY(student_id) REFERENCES users(id)
    )
    """)

    # MESSAGES
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        receiver_id INTEGER, -- Can be User ID or Group ID
        is_group_msg INTEGER DEFAULT 0,
        message TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(sender_id) REFERENCES users(id)
    )
    """)

    # Collaborative Learning tables
    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_groups(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        project_title TEXT,
        description TEXT,
        status TEXT DEFAULT 'Active',
        leader_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(leader_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_group_members(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER,
        student_id INTEGER,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(group_id, student_id),
        FOREIGN KEY(group_id) REFERENCES student_groups(id),
        FOREIGN KEY(student_id) REFERENCES users(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS project_updates(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER,
        message TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(group_id) REFERENCES student_groups(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS student_availability(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        status TEXT DEFAULT 'Available',
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    initial_skills = [
        ('Python', 'Backend', 3), ('JavaScript', 'Frontend', 2), ('React', 'Frontend', 3),
        ('Node.js', 'Backend', 3), ('SQL', 'Database', 2), ('Machine Learning', 'AI/ML', 4),
        ('Docker', 'DevOps', 3), ('Git', 'Tools', 1), ('HTML', 'Frontend', 1),
        ('CSS', 'Frontend', 1), ('Flask', 'Backend', 2), ('Django', 'Backend', 3),
        ('Pandas', 'Data Science', 2), ('TypeScript', 'Frontend', 2), ('Next.js', 'Frontend', 3),
        ('Tailwind', 'Frontend', 1), ('Redis', 'Backend', 2), ('Kubernetes', 'DevOps', 4),
        ('AWS', 'DevOps', 3), ('TensorFlow', 'AI/ML', 4), ('Scikit-Learn', 'AI/ML', 3)
    ]
    cur.executemany("INSERT OR IGNORE INTO skills(name, category, weight) VALUES(?,?,?)", initial_skills)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
