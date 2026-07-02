import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.models import Base, Model


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'test.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_create_model(session):
    m = Model(name="qwen32b", host="10.0.0.1", port=9092,
              model_name="qwen3-32b", concurrency=20,
              model_config_key="local_qwen")
    session.add(m)
    session.commit()
    assert m.id is not None


def test_all_tables_created(session):
    from backend.app.models import (
        Model, JudgeLLM, Task, DatasetVersion, Prediction,
        Evaluation, Batch, BatchCell, BatchRevision, Job,
    )
    engine = session.get_bind()
    tables = set(Base.metadata.tables.keys())
    expected = {"models", "judges", "tasks", "dataset_versions",
                "predictions", "evaluations", "batches",
                "batch_cells", "batch_revisions", "jobs"}
    assert expected <= tables
