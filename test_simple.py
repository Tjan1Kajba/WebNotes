from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
import json


from main import app
client = TestClient(app)


def test_login_page_loads():
    """Simple test: Check if login page loads successfully"""
    response = client.get("/login/")

    assert response.status_code == 200

    content_type = response.headers.get("content-type", "")
    assert "text/html" in content_type

    print("Test passed: Login page loads successfully")


def test_register_endpoint_basic():
    """Simple test: Check if register endpoint accepts POST requests"""
    with patch('main.get_db_conn') as mock_db:
        with patch('main.redis_client') as mock_redis:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = None
            mock_cursor.lastrowid = 1
            mock_db.return_value = mock_conn

            mock_redis.exists.return_value = False
            mock_redis.delete.return_value = True

            with patch('main.hash_password', return_value="hashed_password"):
                response = client.post(
                    "/register/",
                    json={"username": "testuser", "password": "testpass"}
                )
    assert response.status_code == 200

    response_data = response.json()
    assert "message" in response_data
    assert response_data["message"] == "User registered successfully"

    print("Test passed: Register endpoint works with mocked dependencies")


def test_protected_endpoint_requires_auth():
    """Simple test: Check that protected endpoints require authentication"""
    response = client.get("/notes/")
    assert response.status_code == 401

    print("Test passed: Protected endpoint requires authentication")


if __name__ == "__main__":
    print("=" * 50)
    print("Running Simple FastAPI Tests")
    print("=" * 50)

    tests = [
        test_login_page_loads,
        test_register_endpoint_basic,
        test_protected_endpoint_requires_auth,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"{test_func.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"{test_func.__name__} error: {type(e).__name__}: {e}")
            failed += 1

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)

    if failed > 0:
        exit(1)
