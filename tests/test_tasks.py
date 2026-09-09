"""Реестр долгих задач панели.

Съёмка серии — это минуты ожидания и списанные деньги. Задача принадлежит серверу,
а не вкладке браузера: закрытая вкладка не должна обрывать оплаченную генерацию.
"""
import sys
import time

import pytest

from factory.tasks import TaskBusyError, TaskRunner

SLEEP = [sys.executable, "-c", "import time; time.sleep(3)"]


@pytest.fixture
def runner():
    r = TaskRunner(journal_size=5)
    yield r
    r.cancel()          # ни один тест не оставляет живой процесс за собой


def wait_finished(runner, timeout=10.0):
    """Дождаться терминального статуса; тесты не должны висеть вечно."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = runner.current()
        if snap and snap["status"] != "running":
            return snap
        time.sleep(0.02)
    raise AssertionError(f"задача не завершилась за {timeout} с: {runner.current()}")


def test_no_task_at_start(runner):
    assert runner.current() is None


def test_start_returns_running_snapshot(runner):
    snap = runner.start(SLEEP, {"kind": "stage", "stage": "segments",
                                "project": "projects/п", "episode": "ep01"})
    assert snap["status"] == "running"
    assert snap["stage"] == "segments"
    assert snap["exit_code"] is None
    assert snap["id"]


def test_finished_task_keeps_output_and_exit_code(runner):
    runner.start([sys.executable, "-c", "print('снято 3 из 3')"], {"stage": "segments"})
    snap = wait_finished(runner)

    assert snap["status"] == "done"
    assert snap["exit_code"] == 0
    assert "снято 3 из 3" in "\n".join(snap["lines"])
    assert snap["finished_at"] >= snap["started_at"]


def test_nonzero_exit_is_failed(runner):
    """Гейт конвейера выходит кодом 3, и это не «успех с оговоркой»."""
    runner.start([sys.executable, "-c", "import sys; print('гейт закрыт'); sys.exit(3)"],
                 {"stage": "segments"})
    snap = wait_finished(runner)

    assert snap["status"] == "failed"
    assert snap["exit_code"] == 3
    assert "гейт закрыт" in "\n".join(snap["lines"])


def test_stderr_lands_in_the_same_journal(runner):
    """Человек читает один журнал: разделять потоки ему нечем."""
    runner.start([sys.executable, "-c", "import sys; sys.stderr.write('трейсбек\\n')"],
                 {"stage": "segments"})
    snap = wait_finished(runner)
    assert "трейсбек" in "\n".join(snap["lines"])


def test_second_start_while_running_raises(runner):
    runner.start(SLEEP, {"stage": "segments"})
    with pytest.raises(TaskBusyError):
        runner.start(SLEEP, {"stage": "audio"})


def test_start_after_finish_is_allowed(runner):
    runner.start([sys.executable, "-c", "pass"], {"stage": "segments"})
    wait_finished(runner)

    snap = runner.start([sys.executable, "-c", "pass"], {"stage": "audio"})
    assert snap["stage"] == "audio"


def test_cancel_marks_cancelled_and_says_who(runner):
    runner.start(SLEEP, {"stage": "segments"})
    assert runner.cancel() is True

    snap = wait_finished(runner)
    assert snap["status"] == "cancelled"
    assert any("человек" in line for line in snap["lines"]), snap["lines"]


def test_cancel_without_task_is_false(runner):
    assert runner.cancel() is False


def test_journal_is_capped(runner):
    """В памяти живёт хвост, а не весь вывод провайдера."""
    runner.start([sys.executable, "-c", "for i in range(50): print('строка', i)"],
                 {"stage": "segments"})
    snap = wait_finished(runner)

    assert len(snap["lines"]) == 5
    assert "строка 49" in snap["lines"][-1]


def test_snapshot_is_a_copy(runner):
    """Панель не должна портить состояние сервера, читая его."""
    runner.start([sys.executable, "-c", "print('раз')"], {"stage": "segments"})
    snap = wait_finished(runner)
    snap["lines"].append("подделка")

    assert "подделка" not in runner.current()["lines"]


# --- признаки жизни на долгой стадии (2026-09-09) --------------------------

def test_silent_stage_gets_a_heartbeat_in_the_journal():
    """Текстовая стадия молчит до самого ответа — иногда десятки минут.

    Пустой журнал в это время неотличим от зависшей панели: живой прогон
    2026-09-09 закончился таймаутом движка после четверти часа тишины.
    """
    runner = TaskRunner(journal_size=20, heartbeat_seconds=0.05)
    try:
        runner.start([sys.executable, "-c", "import time; time.sleep(0.6)"])
        wait_finished(runner)
    finally:
        runner.cancel()

    lines = runner.current()["lines"]
    assert any("идёт" in line for line in lines), lines


def test_chatty_stage_is_not_interrupted_by_heartbeats():
    """Стадия, которая сама печатает прогресс, в подсказках не нуждается."""
    runner = TaskRunner(journal_size=50, heartbeat_seconds=0.2)
    try:
        runner.start([sys.executable, "-c",
                      "import time\n"
                      "for i in range(6):\n"
                      "    print('снято', i, flush=True)\n"
                      "    time.sleep(0.05)\n"])
        wait_finished(runner)
    finally:
        runner.cancel()

    lines = runner.current()["lines"]
    assert not any("идёт" in line for line in lines), lines


def test_finished_task_calls_the_hook_once():
    """Кому продолжать конвейер, решает сервер — значит и знать об окончании
    задачи он должен сам, а не через опрос из браузера."""
    seen = []
    runner = TaskRunner(journal_size=5, heartbeat_seconds=0)
    runner.on_finished = lambda task: seen.append(task["status"])
    try:
        runner.start([sys.executable, "-c", "print('готово')"])
        wait_finished(runner)
    finally:
        runner.cancel()

    for _ in range(50):
        if seen:
            break
        time.sleep(0.02)
    assert seen == ["done"]


def test_hook_failure_does_not_break_the_runner():
    """Сорвавшийся водитель не должен уносить с собой чтение вывода."""
    runner = TaskRunner(journal_size=5, heartbeat_seconds=0)

    def boom(task):
        raise RuntimeError("водитель сломался")

    runner.on_finished = boom
    try:
        runner.start([sys.executable, "-c", "print('готово')"])
        snap = wait_finished(runner)
    finally:
        runner.cancel()

    assert snap["status"] == "done"
