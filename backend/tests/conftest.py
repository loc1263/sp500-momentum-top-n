import pytest

from top3.config import DEFAULT_CONFIG, DataSettings
from top3.db import open_db


@pytest.fixture
def cfg() -> dict:
    return {section: dict(values) for section, values in DEFAULT_CONFIG.items()}


@pytest.fixture
def settings(cfg) -> DataSettings:
    return DataSettings.from_config(cfg)


@pytest.fixture
def conn(tmp_path):
    c = open_db(tmp_path / "sub" / "t.db")
    yield c
    c.close()
