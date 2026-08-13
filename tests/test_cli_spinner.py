import io
import time

from content_creator import director_chat
from content_creator.director_chat import _CliSpinner, _TerminalInputGuard, _cli_task


def test_spinner_reuses_one_output_line():
    stream = io.StringIO()
    spinner = _CliSpinner(stream=stream, interval=0.01)
    spinner.update("导演助手|正在理解创意需求")
    spinner.start()
    time.sleep(0.035)
    spinner.stop()
    output = stream.getvalue()
    assert "\r" in output
    assert "\n" not in output
    assert "." in output
    assert ".." in output
    assert "..." in output


def test_cli_task_stops_spinner_on_exception():
    stream = io.StringIO()
    try:
        with _cli_task("THINKING", stream=stream) as spinner:
            spinner.update("导演计划|正在解析")
            raise RuntimeError("test")
    except RuntimeError:
        pass
    assert "\n" not in stream.getvalue()


def test_spinner_normalizes_existing_trailing_dots():
    stream = io.StringIO()
    spinner = _CliSpinner(stream=stream, interval=0.01)
    spinner.update("渲染器|正在打包 Remotion 项目...")
    spinner.start()
    time.sleep(0.035)
    spinner.stop()
    assert "...." not in stream.getvalue()


def test_spinner_tty_clears_the_whole_line():
    class TtyStream(io.StringIO):
        def isatty(self):
            return True

    stream = TtyStream()
    spinner = _CliSpinner(stream=stream)
    spinner._write("导演助手 正在处理...")
    spinner.stop()
    assert stream.getvalue().endswith("\r\x1b[2K")


def test_terminal_input_guard_restores_and_flushes(monkeypatch):
    class TtyInput:
        def isatty(self):
            return True

        def fileno(self):
            return 12

    calls = []
    monkeypatch.setattr(director_chat.sys, "stdin", TtyInput())
    monkeypatch.setattr(director_chat.termios, "tcgetattr", lambda fd: [0, 0, 0, director_chat.termios.ECHO | director_chat.termios.ICANON | director_chat.termios.ISIG, 0, 0, []])
    monkeypatch.setattr(director_chat.termios, "tcsetattr", lambda *args: calls.append(("set", args)))
    monkeypatch.setattr(director_chat.termios, "tcflush", lambda *args: calls.append(("flush", args)))
    monkeypatch.setattr(director_chat.select, "select", lambda *args: ([], [], []))

    guard = _TerminalInputGuard()
    guard.start()
    guard.stop()

    assert calls[-1] == ("flush", (12, director_chat.termios.TCIFLUSH))
    active_flags = calls[0][1][2][3]
    assert not active_flags & director_chat.termios.ECHO
    assert not active_flags & director_chat.termios.ICANON
    assert active_flags & director_chat.termios.ISIG


def test_terminal_input_guard_skips_non_tty(monkeypatch):
    calls = []
    monkeypatch.setattr(director_chat.sys, "stdin", io.StringIO())
    monkeypatch.setattr(director_chat.termios, "tcgetattr", lambda *args: calls.append(args))

    guard = _TerminalInputGuard()
    guard.start()
    guard.stop()

    assert calls == []
