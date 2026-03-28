"""main.py PID 처리 단위 테스트"""
import os
import sys
import signal
import tempfile
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import main as m


def test_write_pid_creates_file(tmp_path):
    pid_file = str(tmp_path / "test.pid")
    m.write_pid(pid_file)
    assert os.path.exists(pid_file)
    with open(pid_file) as f:
        assert int(f.read().strip()) == os.getpid()


def test_cleanup_pid_removes_file(tmp_path):
    pid_file = str(tmp_path / "test.pid")
    with open(pid_file, "w") as f:
        f.write("12345")
    m.cleanup_pid(pid_file)
    assert not os.path.exists(pid_file)


def test_cleanup_pid_noop_if_missing(tmp_path):
    pid_file = str(tmp_path / "nonexistent.pid")
    m.cleanup_pid(pid_file)  # 예외 없이 통과해야 함


def test_kill_existing_sends_sigterm(tmp_path):
    pid_file = str(tmp_path / "test.pid")
    with open(pid_file, "w") as f:
        f.write("99999")
    with patch("os.kill") as mock_kill:
        mock_kill.side_effect = ProcessLookupError
        m.kill_existing(pid_file)  # 예외 없이 통과
        mock_kill.assert_called_once_with(99999, signal.SIGTERM)


def test_kill_existing_handles_missing_pid_file(tmp_path):
    pid_file = str(tmp_path / "none.pid")
    m.kill_existing(pid_file)  # 예외 없이 통과


def test_kill_existing_handles_invalid_pid(tmp_path):
    pid_file = str(tmp_path / "test.pid")
    with open(pid_file, "w") as f:
        f.write("not-a-number")
    m.kill_existing(pid_file)  # ValueError 처리, 예외 없이 통과
