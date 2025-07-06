import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from chatbot_server import app, DOCS_DIR, conversations  # noqa: E402

client = TestClient(app)
ADMIN_TOKEN = {"access_token": "admin-token"}


def test_admin_doc_list_and_delete(tmp_path):
    DOCS_DIR.mkdir(exist_ok=True)
    file_path = DOCS_DIR / "sample.txt"
    file_path.write_text("hello")

    resp = client.get("/admin/docs", params=ADMIN_TOKEN)
    assert resp.status_code == 200
    assert "sample.txt" in resp.json()["files"]

    resp = client.delete("/admin/docs/sample.txt", params=ADMIN_TOKEN)
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert not file_path.exists()


def test_admin_clear_history():
    conversations["user1"] = [{"role": "user", "content": "hi", "ts": 0}]
    resp = client.delete("/admin/history/user1", params=ADMIN_TOKEN)
    assert resp.status_code == 200
    assert conversations["user1"] == []
