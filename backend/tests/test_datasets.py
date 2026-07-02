import hashlib
import io

from backend.app.db import get_session
from backend.app.services.seed import seed_generic_tasks


def _seed_task(client):
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        s.commit()
    tid = client.get("/api/v1/tasks").json()[0]["id"]
    return tid


def _make_jsonl_file(content: bytes, filename: str = "data.jsonl"):
    return {"file": (filename, io.BytesIO(content), "application/octet-stream")}


def test_upload_dataset_ok(client):
    tid = _seed_task(client)
    content = b'{"question": "hello"}\n{"question": "world"}\n'
    r = client.post(
        f"/api/v1/tasks/{tid}/datasets",
        data={"tag": "v1", "is_default": True, "note": "first version"},
        files=_make_jsonl_file(content),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["task_id"] == tid
    assert data["tag"] == "v1"
    assert data["is_default"] is True
    assert data["note"] == "first version"
    assert data["content_hash"] == hashlib.sha256(content).hexdigest()
    assert "data.jsonl" in data["data_path"]


def test_upload_dataset_rejects_non_jsonl(client):
    tid = _seed_task(client)
    r = client.post(
        f"/api/v1/tasks/{tid}/datasets",
        data={"tag": "v1"},
        files=_make_jsonl_file(b'{"x": 1}\n', "data.txt"),
    )
    assert r.status_code == 400


def test_upload_dataset_rejects_empty_file(client):
    tid = _seed_task(client)
    r = client.post(
        f"/api/v1/tasks/{tid}/datasets",
        data={"tag": "v1"},
        files=_make_jsonl_file(b"", "data.jsonl"),
    )
    assert r.status_code == 400


def test_upload_dataset_rejects_invalid_jsonl(client):
    tid = _seed_task(client)
    r = client.post(
        f"/api/v1/tasks/{tid}/datasets",
        data={"tag": "v1"},
        files=_make_jsonl_file(b"not json\n", "data.jsonl"),
    )
    assert r.status_code == 400


def test_upload_dataset_task_not_found(client):
    content = b'{"x": 1}\n'
    r = client.post(
        "/api/v1/tasks/99999/datasets",
        data={"tag": "v1"},
        files=_make_jsonl_file(content),
    )
    assert r.status_code == 404


def test_upload_dataset_clears_previous_default(client):
    tid = _seed_task(client)
    content = b'{"x": 1}\n'
    r1 = client.post(
        f"/api/v1/tasks/{tid}/datasets",
        data={"tag": "v1", "is_default": True},
        files=_make_jsonl_file(content),
    )
    assert r1.status_code == 200
    dv1_id = r1.json()["id"]

    r2 = client.post(
        f"/api/v1/tasks/{tid}/datasets",
        data={"tag": "v2", "is_default": True},
        files=_make_jsonl_file(content),
    )
    assert r2.status_code == 200
    dv2_id = r2.json()["id"]

    # 查询确认 v1 的 is_default 已被清除
    r = client.get(f"/api/v1/tasks/{tid}/datasets")
    items = {i["id"]: i for i in r.json()}
    assert items[dv1_id]["is_default"] is False
    assert items[dv2_id]["is_default"] is True


def test_list_datasets(client):
    tid = _seed_task(client)
    content = b'{"x": 1}\n'
    client.post(
        f"/api/v1/tasks/{tid}/datasets",
        data={"tag": "v1"},
        files=_make_jsonl_file(content),
    )
    client.post(
        f"/api/v1/tasks/{tid}/datasets",
        data={"tag": "v2"},
        files=_make_jsonl_file(content),
    )
    r = client.get(f"/api/v1/tasks/{tid}/datasets")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    tags = [i["tag"] for i in items]
    # 按 uploaded_at desc 排序
    assert tags == ["v2", "v1"]


def test_list_datasets_task_not_found(client):
    r = client.get("/api/v1/tasks/99999/datasets")
    assert r.status_code == 404
