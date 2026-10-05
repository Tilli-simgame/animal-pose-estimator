import pytest
from fastapi.testclient import TestClient

from horse_conformation import app as app_module
from horse_conformation import auth, dataset

client = TestClient(app_module.app)
PASSWORD = "salasana-123"


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dataset, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auth, "_failures", {})
    client.cookies.clear()
    auth.create_user("admin", PASSWORD, auth.Role.ADMIN, "Pääkäyttäjä")
    auth.create_user("tuomari", PASSWORD, auth.Role.JUDGE)
    return tmp_path


def login(username: str, password: str = PASSWORD):
    client.cookies.clear()
    return client.post("/api/login", json={"username": username, "password": password})


def test_password_hashing():
    stored = auth.hash_password("oikea-salasana")
    assert "oikea-salasana" not in stored
    assert auth.verify_password("oikea-salasana", stored)
    assert not auth.verify_password("väärä-salasana", stored)
    assert not auth.verify_password("x", "rikki")


def test_pages_and_api_require_login():
    for path in ("/", "/users"):
        res = client.get(path, follow_redirects=False)
        assert res.status_code == 303 and res.headers["location"] == "/login"
    assert client.get("/api/schema").status_code == 401
    assert client.post("/api/analyze", json={"keypoints": {}}).status_code == 401
    assert client.get("/login").status_code == 200


def test_login_logout_and_session_cookie():
    res = login("TUOMARI")  # usernames are case-insensitive
    assert res.status_code == 200
    cookie = res.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/me").json()["user"]["username"] == "tuomari"
    assert client.get("/", follow_redirects=False).status_code == 200

    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401


def test_wrong_password_and_lockout():
    assert login("tuomari", "väärä-salasana").status_code == 401
    assert login("eiole", "väärä-salasana").status_code == 401
    for _ in range(auth.MAX_FAILURES - 1):
        login("tuomari", "väärä-salasana")
    res = login("tuomari")  # even the right password is refused while locked
    assert res.status_code == 401 and "Liian monta" in res.json()["detail"]


def test_judge_cannot_manage_users():
    login("tuomari")
    assert client.get("/api/users").status_code == 403
    assert client.post("/api/users", json={"username": "x", "password": PASSWORD}).status_code == 403
    assert client.get("/users", follow_redirects=False).headers["location"] == "/"


def test_admin_creates_and_manages_users():
    login("admin")
    res = client.post("/api/users", json={"username": "uusi", "display_name": "Uusi Tuomari", "password": PASSWORD})
    assert res.status_code == 200
    new_id = res.json()["user"]["id"]
    assert res.json()["user"]["role"] == "judge"

    assert client.post("/api/users", json={"username": "UUSI", "password": PASSWORD}).status_code == 422
    assert client.post("/api/users", json={"username": "lyhyt", "password": "123"}).status_code == 422
    names = [u["username"] for u in client.get("/api/users").json()["users"]]
    assert names == ["admin", "tuomari", "uusi"]

    # The new user can sign in, then gets signed out when the account is closed
    new_client = TestClient(app_module.app)
    assert new_client.post("/api/login", json={"username": "uusi", "password": PASSWORD}).status_code == 200
    assert client.patch(f"/api/users/{new_id}", json={"active": False}).status_code == 200
    assert new_client.get("/api/me").status_code == 401
    assert new_client.post("/api/login", json={"username": "uusi", "password": PASSWORD}).status_code == 401

    # Re-open the account with a new temporary password
    assert client.patch(f"/api/users/{new_id}", json={"active": True, "password": "uusi-salasana-1"}).status_code == 200
    assert new_client.post("/api/login", json={"username": "uusi", "password": "uusi-salasana-1"}).status_code == 200


def test_admin_cannot_lock_themselves_out():
    login("admin")
    admin_id = client.get("/api/me").json()["user"]["id"]
    assert client.patch(f"/api/users/{admin_id}", json={"role": "judge"}).status_code == 422
    assert client.patch(f"/api/users/{admin_id}", json={"active": False}).status_code == 422
    assert client.patch(f"/api/users/{admin_id}", json={"display_name": "Uusi nimi"}).status_code == 200


def test_change_own_password_signs_out_other_sessions():
    login("tuomari")
    other = TestClient(app_module.app)
    other.post("/api/login", json={"username": "tuomari", "password": PASSWORD})

    assert client.post("/api/me/password", json={"current": "väärä", "new": "uusi-salasana-1"}).status_code == 422
    assert client.post("/api/me/password", json={"current": PASSWORD, "new": "lyhyt"}).status_code == 422
    assert client.post("/api/me/password", json={"current": PASSWORD, "new": "uusi-salasana-1"}).status_code == 200

    assert client.get("/api/me").status_code == 200  # this session stays
    assert other.get("/api/me").status_code == 401  # other devices are signed out
    assert login("tuomari", "uusi-salasana-1").status_code == 200
