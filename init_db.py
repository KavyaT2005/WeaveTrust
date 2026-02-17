import sqlite3

def init_db():
    conn = sqlite3.connect("weavetrust.db")
    c = conn.cursor()

    # USERS (WITH PHONE)
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        phone TEXT
    )
    """)

    # ORDERS
    c.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner TEXT,
        weaver TEXT,
        cloth TEXT,
        meters INTEGER,
        produced INTEGER DEFAULT 0,
        rate INTEGER,
        status TEXT DEFAULT 'Assigned'
    )
    """)

    # HISTORY
    c.execute("""
    CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        weaver TEXT,
        meters INTEGER,
        date TEXT
    )
    """)

    conn.commit()
    conn.close()
    print("✅ Database created successfully!")

if __name__ == "__main__":
    init_db()
