import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
from main import app

client = TestClient(app)


# Test 1: Test preveri, ali prijavna stran vsebuje oba zahtevana obrazca (prijava in registracija)
def test_login_page_structure():
    response = client.get("/login/")
    soup = BeautifulSoup(response.content, 'html.parser')

    login_form = soup.find("form", {"id": "loginForm"})
    register_form = soup.find("form", {"id": "registerForm"})

    assert login_form is not None
    assert register_form is not None

    assert soup.find("input", {"id": "username"}) is not None
    assert soup.find("input", {"id": "password"}) is not None
    assert soup.find("input", {"id": "reg_username"}) is not None
    assert soup.find("input", {"id": "reg_password"}) is not None


# Test 2: Test preverja osnovne HTML strukture (html, head, body, title elementov), ter prisotnost zunanjih knjižnic (Bootstrap, jQuery).
def test_html_structure_validation():
    response = client.get("/login/")
    soup = BeautifulSoup(response.content, 'html.parser')

    assert soup.find("html") is not None
    assert soup.find("head") is not None
    assert soup.find("body") is not None
    assert soup.find("title") is not None

    bootstrap_link = soup.find(
        "link", {"href": lambda x: x and "bootstrap" in x})
    assert bootstrap_link is not None

    jquery_script = soup.find("script", {"src": lambda x: x and "jquery" in x})
    assert jquery_script is not None


# Test 3: Test preveri prisotnost JavaScript elementov, ki omogočajo interaktivnost:
# Obrazec mora imeti definirano submit funkcionalnost
# Stran mora vsebovati jQuery inicializacijski blok (document.ready)
def test_javascript_elements():
    response = client.get("/login/")
    soup = BeautifulSoup(response.content, 'html.parser')

    login_form = soup.find("form", {"id": "loginForm"})
    assert login_form is not None
    assert "submit" in str(login_form)

    scripts = soup.find_all("script")
    has_dom_ready = any("$(document).ready" in str(script)
                        for script in scripts)
    assert has_dom_ready


# Test 4: Test preverja, ali je stran optimizirana za različne velikosti zaslonov (Viewport meta tag, Bootstrap grid sistem)
def test_responsive_design():
    response = client.get("/login/")
    soup = BeautifulSoup(response.content, 'html.parser')

    viewport = soup.find("meta", {"name": "viewport"})
    assert viewport is not None
    assert "width=device-width" in viewport.get("content", "")
    assert soup.find("div", {"class": "col-md-5"}) is not None


# Test 5: Test preveri, ali je za stran nastavljena favicon ikona.
def test_favicon():
    response = client.get("/login/")
    soup = BeautifulSoup(response.content, 'html.parser')

    favicon = soup.find("link", {"rel": "icon"})
    assert favicon is not None
    assert "icon" in favicon.get("href", "")


# Test 6: Test preverja, ali imajo vnosna polja obrazca pravilne HTML atribute za validacijo:
# Polje za uporabniško ime mora biti tipa text
# Polje za geslo mora biti tipa password
def test_form_validation():
    response = client.get("/login/")
    soup = BeautifulSoup(response.content, 'html.parser')

    username_input = soup.find("input", {"id": "username"})
    password_input = soup.find("input", {"id": "password"})

    assert username_input is not None
    assert password_input is not None
    assert username_input.get("type") == "text"
    assert password_input.get("type") == "password"


# Test 7: Test preveri navigacijsko vrstico in prisotnost funkcionalnosti
def test_navigation_bar_elements():
    with patch('main.get_session') as mock_get_session:
        mock_get_session.return_value = {"user_id": 1, "username": "testuser"}

        with patch('main.get_db_conn') as mock_db:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_db.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = []

            with patch('main.redis_client.get') as mock_redis_get:
                mock_redis_get.return_value = None
                client.cookies.set("session_id", "test_session")
                response = client.get("/notes/")

    assert response.status_code == 200
    soup = BeautifulSoup(response.content, 'html.parser')

    navbar = soup.find("nav", {"class": "navbar"})
    assert navbar is not None
    brand = navbar.find("a", {"class": "navbar-brand"})
    assert brand is not None
    assert "BELEŽKA" in brand.text
    add_button_form = soup.find("form", {"id": "addNoteForm"})
    assert add_button_form is not None
    add_button = add_button_form.find("button", {"onclick": "addNote()"})
    assert add_button is not None
    assert "NOV LISTEK" in add_button.text or "📃" in add_button.text
    search_form = soup.find("form", {"action": "/search/"})
    assert search_form is not None
    assert search_form.get("method") == "get"
    search_input = search_form.find("input", {"name": "query"})
    assert search_input is not None
    assert search_input.get("placeholder") == "Išči po naslovu"
    search_button = search_form.find("button", {"type": "submit"})
    assert search_button is not None
    assert "IŠČI" in search_button.text
    scripts = soup.find_all("script")
    script_text = " ".join([str(script) for script in scripts])
    assert "function addNote()" in script_text


# Test 8: Test preveri nogo strani in prikaz uporabniških informacij
def test_footer_and_user_information():
    with patch('main.get_session') as mock_get_session:
        mock_get_session.return_value = {"user_id": 1, "username": "testuser"}

        with patch('main.get_db_conn') as mock_db:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_db.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = []

            with patch('main.redis_client.get') as mock_redis_get:
                mock_redis_get.return_value = None
                client.cookies.set("session_id", "test_session")
                response = client.get("/notes/")

    soup = BeautifulSoup(response.content, 'html.parser')
    footer = soup.find("footer", {"class": "fixed-bottom"})
    assert footer is not None
    footer_text = footer.find("p")
    assert footer_text is not None
    assert "testuser" in footer_text.text
    logout_link = footer.find("a", {"href": "/logout/"})
    assert logout_link is not None
    assert "Odjava" in logout_link.text


# Test 9: Test preveri JavaScript funkcijo za generiranje naključnih barv
def test_random_color_generation_javascript():
    with patch('main.get_session') as mock_get_session:
        mock_get_session.return_value = {"user_id": 1, "username": "testuser"}

        class MockRow:
            def __init__(self, data):
                self.data = data

            def __getitem__(self, key):
                return self.data[key]

            def keys(self):
                return self.data.keys()

        mock_notes = [
            MockRow({"id": 1, "title": "Note 1",
                    "text": "Content 1", "user_id": 1}),
            MockRow({"id": 2, "title": "Note 2",
                    "text": "Content 2", "user_id": 1}),
            MockRow({"id": 3, "title": "Note 3",
                    "text": "Content 3", "user_id": 1})
        ]

        with patch('main.get_db_conn') as mock_db:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_db.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = mock_notes

            with patch('main.redis_client.get') as mock_redis_get:
                mock_redis_get.return_value = None
                client.cookies.set("session_id", "test_session")
                response = client.get("/notes/")

    assert response.status_code == 200
    soup = BeautifulSoup(response.content, 'html.parser')

    scripts = soup.find_all("script")
    script_texts = [str(script) for script in scripts]
    all_script_text = " ".join(script_texts)

    assert "function generateRandomColors(count)" in all_script_text or "function generateRandomColors" in all_script_text
    assert "Math.floor(Math.random() * 16777215)" in all_script_text
    assert ".toString(16)" in all_script_text
    assert "var colors = []" in all_script_text or "let colors = []" in all_script_text or "const colors = []" in all_script_text
    assert "colors.push(color)" in all_script_text or "colors.push" in all_script_text
    assert "generateRandomColors(listeks.length)" in all_script_text or "generateRandomColors(" in all_script_text
    assert "listek.style.backgroundColor" in all_script_text or ".style.backgroundColor" in all_script_text
    assert "#" in all_script_text 
    assert "Math.floor(Math.random() * 16777215)" in all_script_text


# Test 10: Test preveri osnovno strukturo note kartic v HTML
def test_note_card_html_structure():
    with patch('main.get_session') as mock_get_session:
        mock_get_session.return_value = {"user_id": 1, "username": "testuser"}

        class MockRow:
            def __init__(self, data):
                self.data = data

            def __getitem__(self, key):
                return self.data[key]

            def keys(self):
                return self.data.keys()

        mock_notes = [
            MockRow({"id": 1, "title": "Test Naslov",
                    "text": "Test vsebina", "user_id": 1}),
            MockRow({"id": 2, "title": "Druga note",
                    "text": "Več vsebine", "user_id": 1})
        ]

        with patch('main.get_db_conn') as mock_db:
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_db.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchall.return_value = mock_notes

            with patch('main.redis_client.get') as mock_redis_get:
                mock_redis_get.return_value = None
                client.cookies.set("session_id", "test_session")
                response = client.get("/notes/")

    assert response.status_code == 200
    soup = BeautifulSoup(response.content, 'html.parser')

    note_cards = soup.find_all("div", {"class": "listek"})
    assert len(note_cards) == 2

    for card in note_cards:
        assert card.get("data-note-id") is not None
        assert card.get("data-note-id") in ["1", "2"]
        assert "listek" in card.get("class", [])
        assert "mb-4" in card.get("class", [])

    for i, card in enumerate(note_cards, 1):
        delete_form = card.find("form", {"id": f"deleteForm_{i}"})
        assert delete_form is not None
        delete_button = card.find("button", {"class": "btn-danger"})
        assert delete_button is not None
        assert "Zbriši" in delete_button.text
        assert delete_button.get("type") == "button"
        assert "deleteNote(" in delete_button.get("onclick", "")


# 


