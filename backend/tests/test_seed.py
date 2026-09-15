import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.models import Base, Task
from backend.app.services.seed import seed_generic_tasks, seed_custom_tasks


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_seed_generic_tasks_inserts_known_suites(session):
    seed_generic_tasks(session, suite_names=[
        "mmlu_redux_gen_5_shot_str",
        "telequad_gen_0_shot",
    ])
    session.commit()
    t = session.query(Task).filter_by(key="telequad_gen_0_shot").one()
    assert t.type == "generic"
    assert t.is_llm_judge is True  # telequad_gen_0_shot 是 LLM judge 任务


def test_seed_custom_tasks(session):
    seed_custom_tasks(session, task_nums=[34, 36])
    session.commit()
    t = session.query(Task).filter_by(key="task_34_suite").one()
    assert t.type == "custom"
    assert t.custom_task_num == 34
