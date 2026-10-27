from typing import Optional
import json
import os
import uuid
from datetime import datetime, timedelta

import redis
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from pydantic import BaseModel

from database import get_db_connection, initialize_database

initialize_database()

app = FastAPI(title="WebNotes", description="A simple note-taking web application")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
templates = Jinja2Templates(directory="templates")
app.mount("/Slike", StaticFiles(directory="Slike"), name="Slike")

SESSION_EXPIRY_HOURS = 24
SESSION_KEY_PREFIX = "session:"
USER_SESSIONS_PREFIX = "user_sessions:"

redis_available = False
redis_client = None
try:
    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD"),
        db=0,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    redis_client.ping()
    redis_available = True
    print("Redis connected successfully")
except Exception:
    redis_client = None
    print("Redis not available, running without caching")


class UserLogin(BaseModel):
    username: str
    password: str


class UserRegister(BaseModel):
    username: str
    password: str


class NoteCreate(BaseModel):
    title: Optional[str] = "Nov listek"
    text: Optional[str] = ""


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_session(user_id: int, username: str) -> str:
    session_id = str(uuid.uuid4())
    if redis_available and redis_client is not None:
        session_data = {
            "user_id": user_id,
            "username": username,
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
        }
        redis_client.setex(
            f"{SESSION_KEY_PREFIX}{session_id}",
            timedelta(hours=SESSION_EXPIRY_HOURS),
            json.dumps(session_data),
        )
        redis_client.sadd(f"{USER_SESSIONS_PREFIX}{user_id}", session_id)
        redis_client.expire(f"{USER_SESSIONS_PREFIX}{user_id}", timedelta(hours=SESSION_EXPIRY_HOURS))
        return session_id

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sessions (session_id, user_id, username) VALUES (%s, %s, %s)",
        (session_id, user_id, username),
    )
    conn.commit()
    cursor.close()
    conn.close()
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    if not session_id:
        return None
    if redis_available and redis_client is not None:
        session_key = f"{SESSION_KEY_PREFIX}{session_id}"
        raw = redis_client.get(session_key)
        if raw:
            data = json.loads(raw)
            data["last_activity"] = datetime.now().isoformat()
            redis_client.setex(session_key, timedelta(hours=SESSION_EXPIRY_HOURS), json.dumps(data))
            return data
        return None

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username FROM sessions WHERE session_id = %s", (session_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"user_id": row[0], "username": row[1]}
    return None


def delete_session(session_id: str):
    if not session_id:
        return
    if redis_available and redis_client is not None:
        session_key = f"{SESSION_KEY_PREFIX}{session_id}"
        raw = redis_client.get(session_key)
        if raw:
            data = json.loads(raw)
            redis_client.srem(f"{USER_SESSIONS_PREFIX}{data['user_id']}", session_id)
        redis_client.delete(session_key)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))
    conn.commit()
    cursor.close()
    conn.close()


async def get_current_user(request: Request) -> Optional[dict]:
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    return get_session(session_id)


async def require_auth(current_user: Optional[dict] = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return current_user


async def parse_request_data(request: Request, model_cls=None):
    payload = None
    try:
        payload = await request.json()
    except Exception:
        payload = None

    if not payload:
        try:
            form = await request.form()
            if form:
                payload = {key: form.get(key) for key in form.keys()}
        except Exception:
            payload = None

    if payload is None:
        return None
    if model_cls is not None:
        return model_cls(**payload)
    return payload


@app.get("/", include_in_schema=False)
async def root(request: Request):
    session_id = request.cookies.get("session_id")
    logged_in = bool(session_id and get_session(session_id))
    return templates.TemplateResponse("home.html", {"request": request, "logged_in": logged_in})


@app.get("/login", response_class=HTMLResponse)
@app.get("/login/", response_class=HTMLResponse)
async def get_login_page(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and get_session(session_id):
        return RedirectResponse(url="/")
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
@app.get("/register/", response_class=HTMLResponse)
async def get_register_page(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id and get_session(session_id):
        return RedirectResponse(url="/")
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/login")
@app.post("/login/")
async def login(request: Request):
    try:
        data = await parse_request_data(request, UserLogin)
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Username and password are required")

    if data is None or not data.username or not data.password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Username and password are required")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash FROM users WHERE username = %s", (data.username,))
    user_data = cursor.fetchone()
    conn.close()

    if user_data and verify_password(data.password, user_data[2]):
        user_id, username, password_hash = user_data
        if redis_available and redis_client is not None:
            cache_data = {"id": user_id, "username": username, "password_hash": password_hash}
            redis_client.setex(f"user:{username}", timedelta(hours=1), json.dumps(cache_data))

        try:
            login_conn = get_db_connection()
            login_cursor = login_conn.cursor()
            login_is_sqlite = login_conn.__class__.__module__.startswith("sqlite3")
            login_cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?" if login_is_sqlite
                else "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
                (user_id,),
            )
            login_conn.commit()
            login_conn.close()
        except Exception:
            pass

        session_id = create_session(user_id, username)
        response = JSONResponse({"message": "Login successful", "redirect_url": "/"})
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=SESSION_EXPIRY_HOURS * 3600,
            secure=False,
            samesite="lax",
        )
        return response

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")


@app.post("/register")
@app.post("/register/")
async def register(request: Request):
    try:
        data = await parse_request_data(request, UserRegister)
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Username and password are required")

    if data is None or not data.username or not data.password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Username and password are required")

    if len(data.password) < 6:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Password must be at least 6 characters long")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = %s", (data.username,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    password_hash = hash_password(data.password)
    cursor.execute(
        "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
        (data.username, password_hash),
    )
    user_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    if redis_available and redis_client is not None:
        redis_client.delete(f"user:{data.username}")

    return {"message": "User registered successfully", "user_id": user_id}


@app.get("/logout/")
async def logout(request: Request):
    session_id = request.cookies.get("session_id")
    if session_id:
        delete_session(session_id)

    response = RedirectResponse(url="/login/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session_id")
    return response


@app.get("/notes/", response_class=HTMLResponse)
async def read_notes(request: Request, current_user: dict = Depends(require_auth)):
    notes = _get_notes_from_db(current_user["user_id"])
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "notes": notes,
            "username": current_user["username"],
            "show_add_note": True,
            "show_search": True,
        },
    )


def _get_notes_from_db(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = "?" if conn.__class__.__module__.startswith("sqlite3") else "%s"
    cursor.execute(
        f"SELECT id, title, text, created_at, updated_at, is_public, is_pinned FROM notes WHERE user_id = {placeholder} ORDER BY is_pinned DESC, created_at DESC",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "title": row[1],
            "text": row[2],
            "created_at": row[3],
            "updated_at": row[4],
            "is_public": bool(row[5]) if row[5] is not None else False,
            "is_pinned": bool(row[6]) if row[6] is not None else False,
        }
        for row in rows
    ]


def _get_public_notes_from_db(current_user_id: Optional[int] = None, sort_order: str = "date_desc"):
    conn = get_db_connection()
    cursor = conn.cursor()
    order_by = {
        "date_desc": "n.created_at DESC",
        "date_asc": "n.created_at ASC",
        "likes_desc": "heart_count DESC, n.created_at DESC",
        "likes_asc": "heart_count ASC, n.created_at DESC",
    }.get(sort_order, "n.created_at DESC")
    if conn.__class__.__module__.startswith("sqlite3"):
        if current_user_id is None:
            cursor.execute(
                f"""
                SELECT n.id, n.title, n.text, n.created_at, n.updated_at, n.is_public, u.username,
                       COALESCE(hc.heart_count, 0) AS heart_count,
                       0 AS is_hearted
                FROM notes n
                JOIN users u ON u.id = n.user_id
                LEFT JOIN (
                    SELECT note_id, COUNT(*) AS heart_count
                    FROM note_hearts
                    GROUP BY note_id
                ) hc ON hc.note_id = n.id
                WHERE n.is_public = 1
                ORDER BY {order_by}
                """
            )
        else:
            cursor.execute(
                f"""
                SELECT n.id, n.title, n.text, n.created_at, n.updated_at, n.is_public, u.username,
                       COALESCE(hc.heart_count, 0) AS heart_count,
                       CASE WHEN uh.user_id IS NULL THEN 0 ELSE 1 END AS is_hearted
                FROM notes n
                JOIN users u ON u.id = n.user_id
                LEFT JOIN (
                    SELECT note_id, COUNT(*) AS heart_count
                    FROM note_hearts
                    GROUP BY note_id
                ) hc ON hc.note_id = n.id
                LEFT JOIN note_hearts uh ON uh.note_id = n.id AND uh.user_id = ?
                WHERE n.is_public = 1
                ORDER BY {order_by}
                """,
                (current_user_id,),
            )
    else:
        if current_user_id is None:
            cursor.execute(
                f"""
                SELECT n.id, n.title, n.text, n.created_at, n.updated_at, n.is_public, u.username,
                       COALESCE(hc.heart_count, 0) AS heart_count,
                       0 AS is_hearted
                FROM notes n
                JOIN users u ON u.id = n.user_id
                LEFT JOIN (
                    SELECT note_id, COUNT(*) AS heart_count
                    FROM note_hearts
                    GROUP BY note_id
                ) hc ON hc.note_id = n.id
                WHERE n.is_public = TRUE
                ORDER BY {order_by}
                """
            )
        else:
            cursor.execute(
                f"""
                SELECT n.id, n.title, n.text, n.created_at, n.updated_at, n.is_public, u.username,
                       COALESCE(hc.heart_count, 0) AS heart_count,
                       CASE WHEN uh.user_id IS NULL THEN 0 ELSE 1 END AS is_hearted
                FROM notes n
                JOIN users u ON u.id = n.user_id
                LEFT JOIN (
                    SELECT note_id, COUNT(*) AS heart_count
                    FROM note_hearts
                    GROUP BY note_id
                ) hc ON hc.note_id = n.id
                LEFT JOIN note_hearts uh ON uh.note_id = n.id AND uh.user_id = %s
                WHERE n.is_public = TRUE
                ORDER BY {order_by}
                """,
                (current_user_id,),
            )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "title": row[1],
            "text": row[2],
            "created_at": row[3],
            "updated_at": row[4],
            "is_public": bool(row[5]) if row[5] is not None else False,
            "username": row[6],
            "heart_count": row[7] if len(row) > 7 and row[7] is not None else 0,
            "is_hearted": bool(row[8]) if len(row) > 8 else False,
        }
        for row in rows
    ]


@app.get("/board/", response_class=HTMLResponse)
async def public_board(request: Request):
    current_user = await get_current_user(request)
    sort_order = request.query_params.get("sort", "date_desc")
    if sort_order not in {"date_desc", "date_asc", "likes_desc", "likes_asc"}:
        sort_order = "date_desc"
    notes = _get_public_notes_from_db(current_user["user_id"] if current_user else None, sort_order)
    return templates.TemplateResponse(
        "public_board.html",
        {
            "request": request,
            "notes": notes,
            "username": current_user["username"] if current_user else None,
            "show_new_note_on_board": True,
            "sort_order": sort_order,
        },
    )


@app.post("/notes/{note_id}/heart")
async def toggle_heart(note_id: int, current_user: dict = Depends(require_auth)):
    conn = get_db_connection()
    cursor = conn.cursor()
    is_sqlite = conn.__class__.__module__.startswith("sqlite3")

    cursor.execute("SELECT id, is_public FROM notes WHERE id = %s" if not is_sqlite else "SELECT id, is_public FROM notes WHERE id = ?", (note_id,))
    note = cursor.fetchone()
    if not note:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    if not bool(note[1]):
        conn.close()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Note is not public")

    if is_sqlite:
        cursor.execute("SELECT 1 FROM note_hearts WHERE note_id = ? AND user_id = ?", (note_id, current_user["user_id"]))
    else:
        cursor.execute("SELECT 1 FROM note_hearts WHERE note_id = %s AND user_id = %s", (note_id, current_user["user_id"]))
    existing_heart = cursor.fetchone()

    if existing_heart:
        if is_sqlite:
            cursor.execute("DELETE FROM note_hearts WHERE note_id = ? AND user_id = ?", (note_id, current_user["user_id"]))
            cursor.execute("SELECT COUNT(*) FROM note_hearts WHERE note_id = ?", (note_id,))
        else:
            cursor.execute("DELETE FROM note_hearts WHERE note_id = %s AND user_id = %s", (note_id, current_user["user_id"]))
            cursor.execute("SELECT COUNT(*) FROM note_hearts WHERE note_id = %s", (note_id,))
        hearted = False
    else:
        if is_sqlite:
            cursor.execute("INSERT INTO note_hearts (note_id, user_id) VALUES (?, ?)", (note_id, current_user["user_id"]))
            cursor.execute("SELECT COUNT(*) FROM note_hearts WHERE note_id = ?", (note_id,))
        else:
            cursor.execute("INSERT INTO note_hearts (note_id, user_id) VALUES (%s, %s)", (note_id, current_user["user_id"]))
            cursor.execute("SELECT COUNT(*) FROM note_hearts WHERE note_id = %s", (note_id,))
        hearted = True

    heart_count = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    return {"note_id": note_id, "hearted": hearted, "heart_count": heart_count}


@app.post("/notes/")
async def create_note(request: Request, current_user: dict = Depends(require_auth)):
    payload = None
    if request.headers.get("content-type", "").lower().startswith("application/json"):
        try:
            payload = await request.json()
        except Exception:
            payload = None
    if not payload:
        try:
            form = await request.form()
            payload = {"title": form.get("title") or "Nov listek", "text": form.get("text") or ""}
        except Exception:
            payload = {"title": "Nov listek", "text": ""}

    note = NoteCreate(**payload)
    if not note.title or not note.title.strip():
        note.title = "Nov listek"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
           "INSERT INTO notes (user_id, title, text, is_public, created_at, updated_at) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) RETURNING id",
        (current_user["user_id"], note.title, note.text or "", False),
    )
    note_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    if redis_available and redis_client is not None:
        redis_client.delete(f"notes:{current_user['user_id']}")

    return {"message": "Note created successfully", "note_id": note_id}


@app.post("/notes/{note_id}/publish")
async def publish_note(note_id: int, current_user: dict = Depends(require_auth)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM notes WHERE id = %s", (note_id,))
    note_owner = cursor.fetchone()
    if not note_owner:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if note_owner[0] != current_user["user_id"]:
        conn.close()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    cursor.execute(
        "UPDATE notes SET is_public = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
        (note_id,),
    )
    conn.commit()
    conn.close()

    if redis_available and redis_client is not None:
        redis_client.delete(f"notes:{current_user['user_id']}")

    return {"message": "Note published successfully", "published": True}


@app.post("/notes/{note_id}/pin")
async def toggle_pin(note_id: int, current_user: dict = Depends(require_auth)):
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholder = "?" if conn.__class__.__module__.startswith("sqlite3") else "%s"
    cursor.execute(f"SELECT user_id, is_pinned FROM notes WHERE id = {placeholder}", (note_id,))
    note_data = cursor.fetchone()
    if not note_data:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    if note_data[0] != current_user["user_id"]:
        conn.close()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    pinned = not bool(note_data[1])
    cursor.execute(
        f"UPDATE notes SET is_pinned = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE id = {placeholder}",
        (pinned, note_id),
    )
    conn.commit()
    conn.close()

    if redis_available and redis_client is not None:
        redis_client.delete(f"notes:{current_user['user_id']}")

    return {"message": "Note pin state updated", "pinned": pinned}


@app.put("/notes/{note_id}")
async def update_note(request: Request, note_id: int, current_user: dict = Depends(require_auth)):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    note = NoteUpdate(**payload) if payload else NoteUpdate()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM notes WHERE id = %s", (note_id,))
    note_owner = cursor.fetchone()

    if not note_owner:
        conn.close()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    if note_owner[0] != current_user["user_id"]:
        conn.close()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

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
        cursor.execute(f"UPDATE notes SET {', '.join(update_fields)} WHERE id = %s", update_values)
        conn.commit()

    conn.close()

    if redis_available and redis_client is not None:
        redis_client.delete(f"notes:{current_user['user_id']}")

    return {"message": "Note updated successfully"}


@app.delete("/notes/{note_id}")
@app.delete("/delnotes/{note_id}")
async def delete_note(note_id: int, current_user: dict = Depends(require_auth)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id = %s AND user_id = %s", (note_id, current_user["user_id"]))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found or access denied")

    if redis_available and redis_client is not None:
        redis_client.delete(f"notes:{current_user['user_id']}")

    return {"message": "Note deleted successfully"}


@app.get("/search/")
async def search_notes(request: Request, current_user: dict = Depends(require_auth)):
    query = (request.query_params.get("query") or "").strip()
    if not query:
        return RedirectResponse(url="/notes/")

    conn = get_db_connection()
    cursor = conn.cursor()
    is_sqlite = conn.__class__.__module__.startswith("sqlite3")

    if is_sqlite:
        cursor.execute(
            "SELECT id, title, text, created_at, updated_at FROM notes WHERE user_id = ? AND lower(title) LIKE lower(?) ORDER BY created_at DESC",
            (current_user["user_id"], f"%{query}%"),
        )
    else:
        cursor.execute(
            "SELECT id, title, text, created_at, updated_at FROM notes WHERE user_id = %s AND title ILIKE %s ORDER BY created_at DESC",
            (current_user["user_id"], f"%{query}%"),
        )
    rows = cursor.fetchall()
    conn.close()

    notes = [
        {"id": row[0], "title": row[1], "text": row[2], "created_at": row[3], "updated_at": row[4]}
        for row in rows
    ]
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "notes": notes,
            "username": current_user["username"],
            "show_add_note": True,
            "show_search": True,
        },
    )


@app.get("/profile", response_class=HTMLResponse)
async def get_profile(request: Request, current_user: dict = Depends(require_auth)):
    active_sessions = 0
    if redis_available and redis_client is not None:
        try:
            active_sessions = redis_client.scard(f"{USER_SESSIONS_PREFIX}{current_user['user_id']}")
        except Exception:
            active_sessions = 0

    created_at = last_login = None
    notes_count = public_notes_count = hearts_received = 0
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        ph = "?" if conn.__class__.__module__.startswith("sqlite3") else "%s"
        uid = current_user["user_id"]
        cursor.execute(f"SELECT created_at, last_login FROM users WHERE id = {ph}", (uid,))
        row = cursor.fetchone()
        if row:
            created_at, last_login = row
        cursor.execute(
            f"SELECT COUNT(*), COALESCE(SUM(CASE WHEN is_public THEN 1 ELSE 0 END), 0) FROM notes WHERE user_id = {ph}",
            (uid,),
        )
        counts = cursor.fetchone()
        notes_count, public_notes_count = int(counts[0]), int(counts[1])
        cursor.execute(
            f"SELECT COUNT(*) FROM note_hearts h JOIN notes n ON n.id = h.note_id WHERE n.user_id = {ph}",
            (uid,),
        )
        hearts_received = int(cursor.fetchone()[0])
        cursor.close()
        conn.close()
    except Exception:
        pass

    def fmt(value):
        if not value:
            return "ni podatka"
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        return value.strftime("%d. %m. %Y %H:%M")

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "username": current_user["username"],
            "user_id": current_user["user_id"],
            "created_at": fmt(created_at),
            "last_login": fmt(last_login),
            "last_activity": fmt(current_user.get("last_activity") or datetime.now()),
            "notes_count": notes_count,
            "public_notes_count": public_notes_count,
            "hearts_received": hearts_received,
            "active_sessions": active_sessions,
            "redis_available": redis_available,
        },
    )


@app.get("/health")
async def health_check():
    db_status = "ok"
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
    except Exception as exc:
        db_status = f"error: {str(exc)}"

    return {
        "status": "healthy",
        "database": db_status,
        "redis": "available" if redis_available else "unavailable",
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
