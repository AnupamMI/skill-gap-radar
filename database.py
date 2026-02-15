import sqlite3

def init_db():
    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()

    # Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    # Reports table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role_target TEXT,
        strong TEXT,
        moderate TEXT,
        missing TEXT
    )
    """)
    # Teacher rating table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ratings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER,
        skill TEXT,
        rating INTEGER
    )
    """)


    conn.commit()
    conn.close()
