from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from passlib.context import CryptContext
from database import initialize_database, get_db_connection
from fastapi.responses import RedirectResponse
from typing import List
import redis
import uuid
import json
import os
from datetime import datetime, timedelta


# Initialize database on startup
initialize_database()

app = FastAPI(title="WebNotes", description="A simple note-taking web application")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
templates = Jinja2Templates(directory="templates")

SESSION_EXPIRY_HOURS = 24
SESSION_KEY_PREFIX = "session:"
USER_SESSIONS_PREFIX = "user_sessions:"


# Redis setup (optional)
redis_available = False
try:
    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        password=os.getenv('REDIS_PASSWORD'),
        db=0,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5
    )
    redis_client.ping()
    redis_available = True
    print("✅ Redis connected successfully")
except redis.exceptions.ConnectionError:
    redis_client = None
    print("⚠️  Redis not available, running without caching")


class UserLogin(BaseModel):
    username: str
    password: str


class UserRegister(BaseModel):
    username: str
    password: str


class NoteCreate(BaseModel):
    title: str
    text: str


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = None


def create_session(user_id: int, username: str) -> str:
    """Create a new session (with Redis if available)"""
    session_id = str(uuid.uuid4())

    if redis_available:
        session_data = {
            "user_id": user_id,
            "username": username,
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat()
        }
        redis_client.setex(
            f"{SESSION_KEY_PREFIX}{session_id}",
            timedelta(hours=SESSION_EXPIRY_HOURS),
            json.dumps(session_data)
        )
        redis_client.sadd(f"{USER_SESSIONS_PREFIX}{user_id}", session_id)
        redis_client.expire(f"{USER_SESSIONS_PREFIX}{user_id}",
                            timedelta(hours=SESSION_EXPIRY_HOURS))

    return session_id


def get_session(session_id: str) -> Optional[dict]:
    """Retrieve session data (from Redis if available)"""
    if not session_id or not redis_available:
        return None

    session_key = f"{SESSION_KEY_PREFIX}{session_id}"
    session_data = redis_client.get(session_key)

    if session_data:
        data = json.loads(session_data)
        data["last_activity"] = datetime.now().isoformat()
        redis_client.setex(
            session_key,
            timedelta(hours=SESSION_EXPIRY_HOURS),
            json.dumps(data)
        )
        return data
    return None


def delete_session(session_id: str):
    """Delete a session (from Redis if available)"""
    if not redis_available or not session_id:
        return

    session_key = f"{SESSION_KEY_PREFIX}{session_id}"
    session_data = redis_client.get(session_key)

    if session_data:
        data = json.loads(session_data)
        redis_client.srem(
            f"{USER_SESSIONS_PREFIX}{data['user_id']}", session_id)

    redis_client.delete(session_key)


async def get_current_user(request: Request) -> Optional[dict]:
    """Get current user from session cookie"""
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None

    return get_session(session_id)


async def require_auth(current_user: dict = Depends(get_current_user)):
    """Require authentication dependency"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return current_user


def hash_password(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


@app.get("/", include_in_schema=False)
async def root():
    """Redirect to login page"""
    return RedirectResponse(url="/login/")


@app.get("/login/", response_class=HTMLResponse)
async def get_login_page(request: Request):
    """Serve login page"""
    session_id = request.cookies.get("session_id")
    if session_id and get_session(session_id):
        return RedirectResponse(url="/notes/")
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login/")
async def login(user: UserLogin):
    """Login user with JSON data"""
    if not user.username or not user.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username and password are required"
        )

    # Check cache first (if Redis available)
    cache_key = f"user:{user.username}"
    if redis_available:
        cached_user = redis_client.get(cache_key)
        if cached_user:
            user_data = json.loads(cached_user)
            if verify_password(user.password, user_data["password_hash"]):
                session_id = create_session(user_data["id"], user.username)
                response = RedirectResponse(
                    url="/notes/",
                    status_code=status.HTTP_303_SEE_OTHER
                )
                response.set_cookie(
                    key="session_id",
                    value=session_id,
                    httponly=True,
                    max_age=SESSION_EXPIRY_HOURS * 3600,
                    secure=False,
                    samesite="lax"
                )
                return response

    # Check database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, password_hash FROM users WHERE username = %s",
        (user.username,)
    )
    user_data = cursor.fetchone()
    conn.close()

    if user_data and verify_password(user.password, user_data[2]):
        user_id, username, password_hash = user_data

        # Cache user data (if Redis available)
        if redis_available:
            cache_data = {
                "id": user_id,
                "username": username,
                "password_hash": password_hash
            }
            redis_client.setex(cache_key, timedelta(hours=1), json.dumps(cache_data))

        # Create session and redirect
        session_id = create_session(user_id, username)
        response = RedirectResponse(
            url="/notes/",
            status_code=status.HTTP_303_SEE_OTHER
        )
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=SESSION_EXPIRY_HOURS * 3600,
            secure=False,
            samesite="lax"
        )
        return response

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password"
    )


@app.post("/register/")
async def register(user: UserRegister):
    """Register new user with JSON data"""
    if not user.username or not user.password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username and password are required"
        )

    if len(user.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 6 characters long"
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if user already exists
    cursor.execute("SELECT id FROM users WHERE username = %s", (user.username,))
    existing_user = cursor.fetchone()

    if existing_user:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    # Create new user
    hashed_password = hash_password(user.password)
    cursor.execute(
        "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
        (user.username, hashed_password)
    )

    user_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    # Clear cache if Redis available
    if redis_available:
        redis_client.delete(f"user:{user.username}")

    return {
        "message": "User registered successfully",
        "user_id": user_id
    }


@app.get("/logout/")
async def logout(request: Request):
    """Logout user"""
    session_id = request.cookies.get("session_id")
    if session_id:
        delete_session(session_id)

    response = RedirectResponse(
        url="/login/",
        status_code=status.HTTP_303_SEE_OTHER
    )
    response.delete_cookie(key="session_id")
    return response


@app.get("/notes/", response_class=HTMLResponse)
async def read_notes(request: Request, current_user: dict = Depends(require_auth)):
    """Get user's notes"""
    user_id = current_user["user_id"]
    username = current_user["username"]

    # Check cache first (if Redis available)
    cache_key = f"notes:{user_id}"
    if redis_available:
        cached_notes = redis_client.get(cache_key)
        if cached_notes:
            notes = json.loads(cached_notes)
        else:
            notes = _get_notes_from_db(user_id)
            redis_client.setex(cache_key, timedelta(minutes=5), json.dumps(notes))
    else:
        notes = _get_notes_from_db(user_id)

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "notes": notes, "username": username}
    )


def _get_notes_from_db(user_id: int) -> list:
    """Helper function to get notes from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, title, text, created_at, updated_at
        FROM notes
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (user_id,))
    notes = cursor.fetchall()
    conn.close()

    # Convert tuples to dicts
    return [
        {
            "id": note[0],
            "title": note[1],
            "text": note[2],
            "created_at": note[3],
            "updated_at": note[4]
        }
        for note in notes
    ]


@app.post("/notes/")
async def create_note(note: NoteCreate, current_user: dict = Depends(require_auth)):
    """Create a new note"""
    if not note.title.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Note title cannot be empty"
        )

    user_id = current_user["user_id"]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO notes (user_id, title, text) VALUES (%s, %s, %s) RETURNING id",
        (user_id, note.title, note.text or "")
    )
    note_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    # Clear cache if Redis available
    if redis_available:
        redis_client.delete(f"notes:{user_id}")

    return {
        "message": "Note created successfully",
        "note_id": note_id
    }


@app.put("/notes/{note_id}")
async def update_note(
    note_id: int,
    note: NoteUpdate,
    current_user: dict = Depends(require_auth)
):
    """Update an existing note"""
    user_id = current_user["user_id"]

    # Verify ownership
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT user_id FROM notes WHERE id = %s",
        (note_id,)
    )
    note_owner = cursor.fetchone()

    if not note_owner:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found"
        )

    if note_owner[0] != user_id:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # Update note
    update_fields = []
    update_values = []

    if note.title is not None:
        update_fields.append("title = %s")
        update_values.append(note.title)

    if note.text is not None:
        update_fields.append("text = %s")
        update_values.append(note.text)

    if update_fields:
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        update_values.append(note_id)

        cursor.execute(
            f"UPDATE notes SET {', '.join(update_fields)} WHERE id = %s",
            update_values
        )
        conn.commit()

    conn.close()

    # Clear cache if Redis available
    if redis_available:
        redis_client.delete(f"notes:{user_id}")

    return {"message": "Note updated successfully"}


@app.delete("/notes/{note_id}")
async def delete_note(note_id: int, current_user: dict = Depends(require_auth)):
    """Delete a note"""
    user_id = current_user["user_id"]

    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify ownership and delete
    cursor.execute(
        "DELETE FROM notes WHERE id = %s AND user_id = %s",
        (note_id, user_id)
    )

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found or access denied"
        )

    conn.commit()
    conn.close()

    # Clear cache if Redis available
    if redis_available:
        redis_client.delete(f"notes:{user_id}")

    return {"message": "Note deleted successfully"}


@app.get("/profile")
async def get_profile(current_user: dict = Depends(require_auth)):
    """Get user profile information"""
    active_sessions = 0
    if redis_available:
        sessions_key = f"{USER_SESSIONS_PREFIX}{current_user['user_id']}"
        try:
            active_sessions = redis_client.scard(sessions_key)
        except:
            active_sessions = 0

    return {
        "username": current_user["username"],
        "user_id": current_user["user_id"],
        "active_sessions": active_sessions,
        "redis_available": redis_available
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    db_status = "ok"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy",
        "database": db_status,
        "redis": "available" if redis_available else "unavailable",
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
