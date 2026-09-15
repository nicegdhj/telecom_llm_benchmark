"""回归：任务必须按 custom_task_num（非 DB 主键 id）命中各自固定 suite。

历史 bug：worker 用 task.id 选 suite，且把有 init 版本的 generic 任务误当 custom。
生产 seed 顺序为 generic 在前，导致 id≠num：
  - task_1_suite 的 id=20  → 曾跑成 task_20_suite（另一个任务）
  - alarm_data(generic) 的 id=1 → 曾被当 custom 跑 task_1_suite → JSONDecodeError
"""
from backend.app.models import Task
from backend.app.services.worker import resolve_run_target


def test_custom_uses_custom_task_num_not_id():
    # 模拟生产库：task_1_suite 主键 id=20，但 custom_task_num=1
    t = Task(id=20, key="task_1_suite", type="custom",
             suite_name="task_1_suite", custom_task_num=1)
    run_type, num, suite = resolve_run_target(t)
    assert run_type == "custom"
    assert num == 1                      # 不是 20
    assert suite == "task_1_suite"       # 不是 task_20_suite


def test_generic_runs_as_generic_even_with_low_id():
    # alarm_data 主键 id=1，但它是 generic，应跑内置 suite，不当 custom
    t = Task(id=1, key="alarm_data_gen_0_shot", type="generic",
             suite_name="alarm_data_gen_0_shot", custom_task_num=None)
    run_type, num, suite = resolve_run_target(t)
    assert run_type == "generic"
    assert num is None
    assert suite == "alarm_data_gen_0_shot"


def test_custom_without_num_raises():
    import pytest
    t = Task(id=5, key="task_x_suite", type="custom",
             suite_name="task_x_suite", custom_task_num=None)
    with pytest.raises(RuntimeError):
        resolve_run_target(t)
