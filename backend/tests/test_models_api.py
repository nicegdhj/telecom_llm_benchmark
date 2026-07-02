def test_create_model(client):
    payload = {
        "name": "qwen32b",
        "host": "10.0.0.1",
        "port": 9092,
        "model_name": "qwen3-32b",
        "concurrency": 20,
    }
    r = client.post("/api/v1/models", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0
    assert body["name"] == "qwen32b"


def test_list_models(client):
    client.post("/api/v1/models", json={
        "name": "m1", "host": "h", "port": 1, "model_name": "x"})
    r = client.get("/api/v1/models")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_duplicate_name_rejected(client):
    p = {"name": "dup", "host": "h", "port": 1, "model_name": "x"}
    client.post("/api/v1/models", json=p)
    r = client.post("/api/v1/models", json=p)
    assert r.status_code == 409