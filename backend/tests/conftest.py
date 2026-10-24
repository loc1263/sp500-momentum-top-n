import pytest

from top3.config import Config, DataConfig
from top3.db import open_db


@pytest.fixture
def cfg() -> Config:
    return Config()


@pytest.fixture
def settings(cfg) -> DataConfig:
    return cfg.data


@pytest.fixture
def conn(tmp_path):
    c = open_db(tmp_path / "sub" / "t.db")
    yield c
    c.close()
