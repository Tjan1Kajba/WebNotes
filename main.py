from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from passlib.context import CryptContext
from database import initialize_database
from fastapi.responses import RedirectResponse
from fastapi import Form
from typing import List
import sqlite3
import redis
import uuid
import json
from datetime import datetime, timedelta


initialize_database()
app = FastAPI()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
templates = Jinja2Templates(directory="templates")

SESSION_EXPIRY_HOURS = 24
SESSION_KEY_PREFIX = "session:"
USER_SESSIONS_PREFIX = "user_sessions:"


def get_db_conn():
    conn = sqlite3.connect('FastAPI.db')
    conn.row_factory = sqlite3.Row
    return conn


redis_client = redis.Redis(
    host='localhost',
    port=6379,
    db=0,
    decode_responses=True
)


class UserLogin(BaseModel):
    username: str
    password: str


class UserRegister(BaseModel):
    username: str
    password: str


def create_session(user_id: int, username: str) -> str:
    """Create a new session in Redis"""
    session_id = str(uuid.uuid4())
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
    """Retrieve session data from Redis"""
    if not session_id:
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
    """Delete a session from Redis"""
    session_key = f"{SESSION_KEY_PREFIX}{session_id}"
    session_data = redis_client.get(session_key)

    if session_data:
        data = json.loads(session_data)
        redis_client.srem(
            f"{USER_SESSIONS_PREFIX}{data['user_id']}", session_id)

    redis_client.delete(session_key)


def delete_all_user_sessions(user_id: int):
    """Delete all sessions for a user"""
    sessions_key = f"{USER_SESSIONS_PREFIX}{user_id}"
    session_ids = redis_client.smembers(sessions_key)

    for session_id in session_ids:
        redis_client.delete(f"{SESSION_KEY_PREFIX}{session_id}")

    redis_client.delete(sessions_key)


async def get_current_user(request: Request) -> Optional[dict]:
    """Dependency to get current user from session"""
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None

    session_data = get_session(session_id)
    return session_data


async def require_auth(current_user: dict = Depends(get_current_user)):
    """Dependency that requires authentication"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return current_user


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password):
    return pwd_context.hash(password)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/login/")


@app.get("/login/", response_class=HTMLResponse)
async def get_login_page(request: Request):

    session_id = request.cookies.get("session_id")
    if session_id and get_session(session_id):
        return RedirectResponse(url="/notes/")
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login/")
async def login(user: UserLogin):
    cache_key = f"user:{user.username}"
    cached_user = redis_client.get(cache_key)

    if cached_user:
        user_data = json.loads(cached_user)
        if verify_password(user.password, user_data["password_hash"]):
            session_id = create_session(user_data["id"], user.username)

            response = RedirectResponse(
                url="/notes/", status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(
                key="session_id",
                value=session_id,
                httponly=True,
                max_age=SESSION_EXPIRY_HOURS * 3600,
                secure=False,
                samesite="lax"
            )
            return response

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, password_hash FROM users WHERE username=?",
        (user.username,)
    )
    user_data = cursor.fetchone()
    conn.close()

    if user_data:
        user_id, username, password_hash = user_data

        if verify_password(user.password, password_hash):
            user_cache_data = {
                "id": user_id,
                "username": username,
                "password_hash": password_hash
            }
            redis_client.setex(
                cache_key,
                timedelta(hours=1),
                json.dumps(user_cache_data)
            )

            session_id = create_session(user_id, username)

            response = RedirectResponse(
                url="/notes/", status_code=status.HTTP_303_SEE_OTHER)
            response.set_cookie(
                key="session_id",
                value=session_id,
                httponly=True,
                max_age=SESSION_EXPIRY_HOURS * 3600,
                secure=False,
                samesite="lax"
            )
            return response

    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/register/")
async def register(user: UserRegister):
    conn = get_db_conn()
    cursor = conn.cursor()

    cache_key = f"user:{user.username}"
    if redis_client.exists(cache_key):
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")

    cursor.execute("SELECT * FROM users WHERE username=?", (user.username,))
    existing_user = cursor.fetchone()

    if existing_user:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed_password = hash_password(user.password)

    cursor.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (user.username, hashed_password)
    )
    conn.commit()

    user_id = cursor.lastrowid

    conn.close()

    redis_client.delete("all_users")

    return {"message": "User registered successfully", "user_id": user_id}


@app.get("/logout/")
async def logout(request: Request):
    """Logout user by deleting session"""
    session_id = request.cookies.get("session_id")
    if session_id:
        delete_session(session_id)

    response = RedirectResponse(
        url="/login/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session_id")
    return response


@app.get("/notes/", response_class=HTMLResponse)
async def read_notes(request: Request, current_user: dict = Depends(require_auth)):
    username = current_user["username"]
    user_id = current_user["user_id"]

    cache_key = f"notes:{user_id}"
    cached_notes = redis_client.get(cache_key)

    if cached_notes:
        notes = json.loads(cached_notes)
    else:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT notes.*, users.username 
            FROM notes 
            JOIN users ON notes.user_id = users.id 
            WHERE users.id = ? 
            ORDER BY notes.id DESC
        ''', (user_id,))
        notes = [dict(row) for row in cursor.fetchall()]
        conn.close()

        redis_client.setex(cache_key, timedelta(minutes=5), json.dumps(notes))

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "notes": notes, "username": username}
    )


@app.post("/notes/", response_class=HTMLResponse)
async def create_item(
    request: Request,
    title: Optional[str] = None,
    text: Optional[List[str]] = None,
    current_user: dict = Depends(require_auth)
):
    if title is None and text is None:
        title = "Naslov"
        text = ["Vsebina"]

    username = current_user["username"]
    user_id = current_user["user_id"]

    conn = get_db_conn()
    cursor = conn.cursor()
    for item_text in text:
        cursor.execute(
            'INSERT INTO notes (user_id, title, text) VALUES (?, ?, ?)',
            (user_id, title, item_text)
        )
    conn.commit()

    redis_client.delete(f"notes:{user_id}")

    cursor.execute(
        'SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC', (user_id,))
    notes = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "notes": notes, "username": username}
    )


@app.put("/notes/{item_id}")
async def update_item(
    item_id: int,
    request: Request,
    current_user: dict = Depends(require_auth)
):
    data = await request.json()
    title = data.get("title")
    text = data.get("text")
    user_id = current_user["user_id"]

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM notes WHERE id = ?', (item_id,))
    existing_item = cursor.fetchone()

    if existing_item is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    if existing_item["user_id"] != user_id:
        conn.close()
        raise HTTPException(
            status_code=403, detail="Not authorized to update this note")

    cursor.execute(
        'UPDATE notes SET title = ?, text = ? WHERE id = ?',
        (title, text, item_id)
    )
    conn.commit()
    conn.close()

    redis_client.delete(f"notes:{user_id}")

    return {"message": "Note updated successfully"}


@app.delete("/delnotes/{item_id}")
def delete_item(
    item_id: int,
    current_user: dict = Depends(require_auth)
):
    user_id = current_user["user_id"]

    conn = get_db_conn()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM notes WHERE id = ?', (item_id,))
    existing_item = cursor.fetchone()

    if existing_item is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    if existing_item["user_id"] != user_id:
        conn.close()
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this note")

    cursor.execute('DELETE FROM notes WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

    redis_client.delete(f"notes:{user_id}")

    return {"message": "Item deleted successfully"}


@app.get("/search/", response_class=HTMLResponse)
async def search_notes(
    request: Request,
    query: str,
    current_user: dict = Depends(require_auth)
):
    user_id = current_user["user_id"]
    username = current_user["username"]

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM notes WHERE user_id = ? AND title LIKE ?",
        (user_id, '%' + query + '%')
    )
    notes = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "notes": notes, "username": username}
    )


@app.get("/profile")
async def get_profile(current_user: dict = Depends(require_auth)):
    sessions_key = f"{USER_SESSIONS_PREFIX}{current_user['user_id']}"
    active_sessions = redis_client.scard(sessions_key)

    return {
        "username": current_user["username"],
        "user_id": current_user["user_id"],
        "active_sessions": active_sessions,
        "last_activity": current_user.get("last_activity")
    }
