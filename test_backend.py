import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from main import app, hash_password, verify_password

client = TestClient(app)


# Test 1: Preveri, da se korenski URL preusmeri na prijavo
def test_root_redirects_to_login():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert "/login/" in response.headers.get("location", "")


# Test 2: Testira validacijo registracijskega endpointa - preverja napačne vnose
def test_register_endpoint_validation():
    response = client.post("/register/", json={})
    assert response.status_code == 422

    response = client.post("/register/", json={"username": "test"})
    assert response.status_code == 422


# Test 3: Testira validacijo prijavnega endpointa - preverja manjkajoče podatke
def test_login_endpoint_validation():
    response = client.post("/login/", json={})
    assert response.status_code == 422

    response = client.post("/login/", json={"username": "test"})
    assert response.status_code == 422


# Test 4: Simulira neuspešno prijavo z napačnimi podatki
def test_login_invalid_credentials_mocked():
    with patch('main.redis_client.get') as mock_redis_get, \
            patch('main.get_db_conn') as mock_get_db:

        mock_redis_get.return_value = None
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_get_db.return_value = mock_conn

        response = client.post(
            "/login/",
            json={"username": "wronguser", "password": "wrongpass"}
        )

    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


# Test 5: Preveri, da zaščitene poti brez avtentikacije vrnejo 401
def test_protected_endpoint_without_auth():
    response = client.get("/notes/")
    assert response.status_code == 401
    assert "Not authenticated" in response.json()["detail"]


# Test 6: Simulira dostop do zaščitene poti z veljavno sejo
def test_protected_endpoint_with_auth_mocked():
    mock_user = {"user_id": 1, "username": "testuser"}

    with patch('main.get_session') as mock_get_session:
        mock_get_session.return_value = mock_user

        with patch('main.get_db_conn') as mock_get_db, \
                patch('main.redis_client.get') as mock_redis_get:

            mock_redis_get.return_value = None
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = []
            mock_get_db.return_value = mock_conn

            response = client.get(
                "/notes/",
                cookies={"session_id": "test_session"}
            )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


# Test 7: Simulira ustvarjanje beležke z avtentikacijo
def test_create_note_endpoint_mocked():
    mock_user = {"user_id": 1, "username": "testuser"}

    with patch('main.get_session') as mock_get_session:
        mock_get_session.return_value = mock_user

        with patch('main.get_db_conn') as mock_get_db, \
                patch('main.redis_client.delete') as mock_redis_delete:

            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = []
            mock_get_db.return_value = mock_conn
            mock_redis_delete.return_value = True

            response = client.post(
                "/notes/",
                cookies={"session_id": "test_session"}
            )

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


# Test 8: Testira funkcionalnost odjave in čiščenje piškotkov
def test_logout():
    with patch('main.delete_session') as mock_delete_session:
        response = client.get("/logout/", follow_redirects=False)

    assert response.status_code == 303
    assert "/login/" in response.headers.get("location", "")
    cookie_header = response.headers.get("set-cookie", "")
    assert "session_id" in cookie_header
    assert "max-age=0" in cookie_header or "expires=" in cookie_header.lower()


# Test 9: Testira čiste funkcije za zgoščevanje in preverjanje gesel
def test_password_functions():
    password = "test_password_123"
    hashed = hash_password(password)

    assert verify_password(password, hashed) == True
    assert verify_password("wrong_password", hashed) == False

    password2 = "different_password"
    hashed2 = hash_password(password2)
    assert hashed != hashed2


# Test 10: Preveri, da registracija ne uspe, če uporabnik že obstaja
def test_register_fails_with_existing_user():
    with patch('main.get_db_conn') as mock_db:
        with patch('main.redis_client') as mock_redis:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor

            mock_cursor.fetchone.return_value = {
                "username": "obstojeci_uporabnik"}
            mock_db.return_value = mock_conn

            mock_redis.exists.return_value = False

            response = client.post(
                "/register/",
                json={"username": "obstojeci_uporabnik",
                      "password": "novogeslo123"}
            )

    assert response.status_code == 400
    assert "Username already exists" in response.json()["detail"]


# Test 11: Preveri celoten proces registracije
def test_register_works_correctly():
    with patch('main.get_db_conn') as mock_db:
        with patch('main.redis_client') as mock_redis:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = None
            mock_cursor.lastrowid = 123
            mock_db.return_value = mock_conn

            mock_redis.exists.return_value = False
            mock_redis.delete.return_value = True

            with patch('main.hash_password', return_value="hashed_password_123"):
                response = client.post(
                    "/register/",
                    json={"username": "nov_uporabnik",
                          "password": "mojegeslo123"}
                )

    assert response.status_code == 200
    response_data = response.json()
    assert "message" in response_data
    assert response_data["message"] == "User registered successfully"
    assert "user_id" in response_data
    assert response_data["user_id"] == 123

    mock_cursor.execute.assert_any_call(
        "SELECT * FROM users WHERE username=?",
        ("nov_uporabnik",)
    )
    mock_cursor.execute.assert_any_call(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        ("nov_uporabnik", "hashed_password_123")
    )
    mock_conn.commit.assert_called_once()
    mock_redis.delete.assert_called_once_with("all_users")
