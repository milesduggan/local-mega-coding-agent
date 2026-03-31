# tests/test_history.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.agent.history import HistoryLog


def test_empty_log_returns_empty_list():
    log = HistoryLog()
    assert log.to_list() == []


def test_add_single_event():
    log = HistoryLog()
    log.add("Read file", "auth.py (120 lines)")
    result = log.to_list()
    assert len(result) == 1
    assert result[0]["title"] == "Read file"
    assert result[0]["detail"] == "auth.py (120 lines)"


def test_add_preserves_order():
    log = HistoryLog()
    log.add("First", "a")
    log.add("Second", "b")
    log.add("Third", "c")
    result = log.to_list()
    assert [e["title"] for e in result] == ["First", "Second", "Third"]


def test_to_list_returns_dicts():
    log = HistoryLog()
    log.add("Tool used", "detail here")
    result = log.to_list()
    assert isinstance(result[0], dict)
    assert set(result[0].keys()) == {"title", "detail"}


def test_multiple_logs_are_independent():
    log1 = HistoryLog()
    log2 = HistoryLog()
    log1.add("In log1", "x")
    assert log2.to_list() == []
