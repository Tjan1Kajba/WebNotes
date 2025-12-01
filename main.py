from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from passlib.context import CryptContext
from database import initialize_database
from fastapi.responses import RedirectResponse
from fastapi import Form
from typing import List
import sqlite3

initialize_database()

app = FastAPI()


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

templates = Jinja2Templates(directory="templates")


def get_db_conn():
    conn = sqlite3.connect('FastAPI.db')
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/login/")


class UserLogin(BaseModel):
    username: str
    password: str


class UserRegister(BaseModel):
    username: str
    password: str


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password):
    return pwd_context.hash(password)


@app.get("/login/", response_class=HTMLResponse)
async def get_login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login/")
async def login(user: UserLogin):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, password_hash FROM users WHERE username=?", (user.username,))
    user_data = cursor.fetchone()
    conn.close()
    if user_data:
        username, password_hash = user_data
        if verify_password(user.password, password_hash):
            return {"message": "Login successful"}
    raise HTTPException(status_code=401, detail="Napaka")


@app.post("/register/")
async def register(user: UserRegister):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=?", (user.username,))
    existing_user = cursor.fetchone()
    conn.close()
    if existing_user:
        raise HTTPException(
            status_code=400, detail="Uporabniško ime že obstaja")

    hashed_password = hash_password(user.password)

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                   (user.username, hashed_password))
    conn.commit()
    conn.close()

    return {"message": "Uporabnik uspešno registriran"}


@app.get("/notes/", response_class=HTMLResponse)
async def read_notes(request: Request):
    username = request.query_params.get("username")
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT notes.*, users.username 
    FROM notes 
    JOIN users ON notes.user_id = users.id 
    WHERE users.username = ? 
    ORDER BY notes.id DESC
''', (username,))

    notes = cursor.fetchall()
    conn.close()

    return templates.TemplateResponse("index.html", {"request": request, "notes": notes, "username": username})


@app.get("/notes/{user_id}")
def read_item(user_id: int):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM notes WHERE user_id = ?', (user_id,))
    item = cursor.fetchall()
    conn.close()
    if item:
        return item
    else:
        raise HTTPException(status_code=404, detail="Item not found")


@app.get("/search/", response_class=HTMLResponse)
async def search_notes(request: Request, query: str):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notes WHERE title LIKE ?",
                   ('%' + query + '%',))
    notes = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "notes": notes})


@app.post("/notes/", response_class=HTMLResponse)
async def create_item(request: Request, title: Optional[str] = None, text: Optional[List[str]] = None):
    if title is None and text is None:
        title = "Naslov"
        text = ["Vsebina"]

    username = request.query_params.get("username")

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user_id = cursor.fetchone()
    conn.close()

    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    conn = get_db_conn()
    cursor = conn.cursor()
    for item_text in text:
        cursor.execute('INSERT INTO notes (user_id, title, text) VALUES (?, ?, ?)',
                       (user_id['id'], title, item_text))
    conn.commit()

    cursor.execute('SELECT * FROM notes ORDER BY id DESC')
    notes = cursor.fetchall()

    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "notes": notes})


@app.put("/notes/{item_id}")
async def update_item(item_id: int, request: Request):
    data = await request.json()
    title = data.get("title")
    text = data.get("text")

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM notes WHERE id = ?', (item_id,))
    existing_item = cursor.fetchone()
    conn.close()
    if existing_item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE notes SET title = ?, text = ? WHERE id = ?', (title, text, item_id))
    conn.commit()
    conn.close()

    return {"message": "Note updated successfully"}


@app.delete("/delnotes/{item_id}")
def delete_item(item_id: int):
    conn = get_db_conn()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM notes WHERE id = ?', (item_id,))
    existing_item = cursor.fetchone()
    if existing_item is None:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    cursor.execute('DELETE FROM notes WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

    return {"message": "Item deleted successfully"}
