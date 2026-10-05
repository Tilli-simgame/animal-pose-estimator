import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from horse_conformation import app as app_module
from horse_conformation import auth, dataset

from .test_rules import HORSE

# No `with` block: the app lifespan (pose model loading) is not run
client = TestClient(app_module.app)

PASSWORD = "salasana-123"


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dataset, "DATA_DIR", tmp_path)
    auth.create_user("tuomari", PASSWORD, auth.Role.JUDGE)
    client.cookies.clear()
    login("tuomari")
    return tmp_path


def login(username: str) -> None:
    client.cookies.clear()
    assert client.post("/api/login", json={"username": username, "password": PASSWORD}).status_code == 200


def jpeg_with_exif() -> bytes:
    img = Image.new("RGB", (1200, 1100), "brown")
    exif = Image.Exif()
    exif[0x010F] = "CameraMaker"  # Make
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def payload(**horse) -> dict:
    return {
        "horse": {"breed": "Suomenhevonen", "type": "kylmäverinen_kevyt", "sex": "ori", "age_years": 4.5,
                  "irl": {"award": "II"}, "url": {"award": "I"}, "link": "https://example.com/hevonen",
                  **horse},
        "keypoints": {k: {"x": x, "y": y, "source": "user"} for k, (x, y) in HORSE.items()},
        "verified": True,
        "original_filename": "oma.jpg",
    }


def create(data: dict):
    return client.post("/api/samples", files={"file": ("oma.jpg", jpeg_with_exif(), "image/jpeg")},
                       data={"data": json.dumps(data)})


def test_create_sample_stores_image_and_annotation(tmp_data_dir):
    res = create(payload())
    assert res.status_code == 200, res.text
    sample_id = res.json()["id"]
    assert res.json()["count"] == 1

    ann = json.loads((tmp_data_dir / "annotations" / f"{sample_id}.json").read_text(encoding="utf-8"))
    assert ann["horse"]["type"] == "kylmäverinen_kevyt"
    assert ann["horse"]["irl"]["award"] == "II"
    assert ann["horse"]["url"]["award"] == "I"
    assert ann["verified"] is True
    assert (ann["width"], ann["height"]) == (1200, 1100)
    assert {f["id"] for f in ann["findings"]} >= {"shoulder_slope", "uphill"}

    image = Image.open(tmp_data_dir / ann["image"])
    assert image.size == (1200, 1100)
    assert len(image.getexif()) == 0  # camera/GPS metadata stripped


def test_update_sample_keeps_image_and_created(tmp_data_dir):
    sample_id = create(payload()).json()["id"]
    before = json.loads((tmp_data_dir / "annotations" / f"{sample_id}.json").read_text(encoding="utf-8"))

    changed = payload(sex="ruuna")
    changed["keypoints"]["withers"]["x"] += 10
    res = client.put(f"/api/samples/{sample_id}", json=changed)
    assert res.status_code == 200, res.text

    after = json.loads((tmp_data_dir / "annotations" / f"{sample_id}.json").read_text(encoding="utf-8"))
    assert after["horse"]["sex"] == "ruuna"
    assert after["keypoints"]["withers"]["x"] == before["keypoints"]["withers"]["x"] + 10
    assert after["created"] == before["created"]
    assert after["image"] == before["image"]
    assert client.get("/api/samples/count").json() == {"count": 1}


def test_metadata_is_optional():
    data = payload()
    data["horse"] = {}
    assert create(data).status_code == 200


def test_invalid_values_are_rejected():
    assert create(payload(type="aasi")).status_code == 422
    assert create(payload(age_years=-1)).status_code == 422
    assert create(payload(irl={"award": "IV"})).status_code == 422
    data = payload()
    del data["keypoints"]["withers"]
    assert create(data).status_code == 422


def test_update_unknown_or_malicious_id():
    assert client.put("/api/samples/20990101-000000-abcdef", json=payload()).status_code == 404
    assert client.put("/api/samples/..%2F..%2Fsecret", json=payload()).status_code == 404


def test_sample_records_owner_and_others_cannot_edit(tmp_data_dir):
    sample_id = create(payload()).json()["id"]
    ann = json.loads((tmp_data_dir / "annotations" / f"{sample_id}.json").read_text(encoding="utf-8"))
    assert ann["created_by"] == "tuomari"

    auth.create_user("toinen", PASSWORD, auth.Role.JUDGE)
    login("toinen")
    assert client.put(f"/api/samples/{sample_id}", json=payload()).status_code == 403

    auth.create_user("admin", PASSWORD, auth.Role.ADMIN)
    login("admin")
    assert client.put(f"/api/samples/{sample_id}", json=payload()).status_code == 200


def test_saving_requires_login():
    client.cookies.clear()
    assert create(payload()).status_code == 401
