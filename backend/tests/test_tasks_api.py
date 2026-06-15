from backend.app.db import get_session
from backend.app.services.seed import seed_generic_tasks, seed_custom_tasks


def _seed():
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        seed_custom_tasks(s, [34])
        s.commit()


def test_list_tasks(client):
    _seed()
    r = client.get("/api/v1/tasks")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    keys = {t["key"] for t in items}
    assert keys == {"mmlu_redux_gen_5_shot_str", "task_34_suite"}


def test_list_excludes_non_whitelisted(client):
    """非白名单任务（如 humaneval）即使入库也不应展示。"""
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str", "humaneval_gen_0_shot"])
        s.commit()
    items = client.get("/api/v1/tasks").json()
    keys = {t["key"] for t in items}
    assert "mmlu_redux_gen_5_shot_str" in keys
    assert "humaneval_gen_0_shot" not in keys


def test_list_ordered_by_script(client):
    """展示顺序应对齐脚本：自定义任务在通用任务之前。"""
    with get_session() as s:
        seed_generic_tasks(s, ["ceval_gen_0_shot_str"])
        seed_custom_tasks(s, [1])
        s.commit()
    keys = [t["key"] for t in client.get("/api/v1/tasks").json()]
    assert keys == ["task_1_suite", "ceval_gen_0_shot_str"]


def test_get_task(client):
    _seed()
    r = client.get("/api/v1/tasks")
    tid = r.json()[0]["id"]
    r2 = client.get(f"/api/v1/tasks/{tid}")
    assert r2.status_code == 200
    data = r2.json()
    assert "key" in data
    assert "type" in data
    assert "suite_name" in data


def test_get_task_404(client):
    r = client.get("/api/v1/tasks/99999")
    assert r.status_code == 404
