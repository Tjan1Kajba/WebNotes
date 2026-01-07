import os
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse


def get_db_connection():
    """Get database connection from DATABASE_URL environment variable"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = os.getenv('LOCAL_DATABASE_URL', 'postgresql://localhost/webnotes')

    parsed = urlparse(database_url)
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/')
    )


def initialize_database():
    """Initialize PostgreSQL database tables"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            username TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_notes_user_id ON notes(user_id)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON sessions(session_id)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)
    ''')

    conn.commit()
    cursor.close()
    conn.close()


def test_connection():
    """Test database connection"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False


if __name__ == "__main__":
    if test_connection():
        print("Database connection successful")
        initialize_database()
        print("Database initialized successfully")
    else:
        print("Failed to connect to database")
