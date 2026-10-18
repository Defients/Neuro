import pytest
from backend.storage import Store

@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'sessions.sqlite3')
