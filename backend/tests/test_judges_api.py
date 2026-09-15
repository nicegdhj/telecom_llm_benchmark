def test_create_judge(client):
    payload = {
        "name": "judge-qwen-plus",
        "host": "dashscope",
        "port": 443,
        "model_name": "qwen-plus",
    }
    r = client.post("/api/v1/judges", json=payload)
    assert r.status_code == 201
    assert r.json()["name"] == "judge-qwen-plus"


def test_list_judges(client):
    client.post("/api/v1/judges", json={
        "name": "j1", "host": "h", "port": 1, "model_name": "x"})
    r = client.get("/api/v1/judges")
    assert len(r.json()) == 1