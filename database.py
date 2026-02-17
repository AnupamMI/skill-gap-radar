import sqlite3

DB = "skillgap.db"

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # USERS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    # REPORTS
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

    # RATINGS (Teacher feedback)
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


# ---------------- CHAT SYSTEM ----------------
def init_chat():
    conn = sqlite3.connect("skillgap.db")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS chats(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER,
        user_id INTEGER,
        message TEXT,
        sender TEXT,
        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


# ---------------- MESSENGER SYSTEM ----------------
def init_messenger():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Conversation (chat room)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS conversations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        is_group INTEGER DEFAULT 0,
        name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Members inside conversation
    cur.execute("""
    CREATE TABLE IF NOT EXISTS participants(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER,
        user_id INTEGER
    )
    """)

    # Messages
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER,
        sender_id INTEGER,
        message TEXT,
        media TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Contacts (friend system)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS contacts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        contact_id INTEGER
    )
    """)

    conn.commit()
    conn.close()
