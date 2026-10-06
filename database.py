import os
import sqlite3
from urllib.parse import urlparse

try:
    import psycopg2
except Exception:  # pragma: no cover
    psycopg2 = None


def get_db_connection():
    """Get a database connection from DATABASE_URL, with SQLite as a local fallback."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        database_url = os.getenv('LOCAL_DATABASE_URL', 'sqlite:///./FastAPI.db')

    if database_url.startswith('sqlite'):
        parsed = urlparse(database_url)
        db_path = parsed.path
        if db_path == ':memory:':
            db_path = ':memory:'
        else:
            db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), db_path.lstrip('/')))
        return sqlite3.connect(db_path, check_same_thread=False)

    if psycopg2 is None:
        raise RuntimeError('psycopg2 is required for PostgreSQL connections but is not installed.')

    parsed = urlparse(database_url)
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip('/')
    )


def initialize_database():
    """Initialize app tables in PostgreSQL or SQLite."""
    conn = get_db_connection()
    cursor = conn.cursor()
    is_sqlite = conn.__class__.__module__.startswith('sqlite3')

    if is_sqlite:
        user_table = '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        '''
        note_table = '''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER NOT NULL,
                is_public BOOLEAN DEFAULT FALSE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        '''
        heart_table = '''
            CREATE TABLE IF NOT EXISTS note_hearts (
                note_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (note_id, user_id),
                FOREIGN KEY(note_id) REFERENCES notes(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        '''
        session_table = '''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        '''
    else:
        user_table = '''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        '''
        note_table = '''
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                is_public BOOLEAN DEFAULT FALSE
            )
        '''
        heart_table = '''
            CREATE TABLE IF NOT EXISTS note_hearts (
                note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (note_id, user_id)
            )
        '''
        session_table = '''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                username TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''

    cursor.execute(user_table)
    cursor.execute(note_table)
    cursor.execute(heart_table)
    cursor.execute(session_table)

    if is_sqlite:
        cursor.execute('PRAGMA table_info(notes)')
        columns = [column[1] for column in cursor.fetchall()]
        if 'is_public' not in columns:
            cursor.execute('ALTER TABLE notes ADD COLUMN is_public BOOLEAN DEFAULT FALSE')
    else:
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'notes' AND column_name = 'is_public'
        """)
        if cursor.fetchone() is None:
            cursor.execute('ALTER TABLE notes ADD COLUMN is_public BOOLEAN DEFAULT FALSE')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_user_id ON notes(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_public ON notes(is_public)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_note_hearts_note_id ON note_hearts(note_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_note_hearts_user_id ON note_hearts(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON sessions(session_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)')

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
