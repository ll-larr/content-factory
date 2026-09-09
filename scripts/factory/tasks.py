"""Долгие задачи панели: одна за раз, живёт в сервере.

Панель запускает те же CLI, что и человек в терминале, — `generate_batch.py` и
`render.py`. Логика гейтов, смет и трат не дублируется: это буквально один код, и
разъехаться панели с командной строкой негде.

Задача принадлежит СЕРВЕРУ, а не вкладке. Съёмка серии — минуты ожидания и
списанные деньги; случайно закрытая вкладка не должна обрывать оплаченную
генерацию, поэтому браузер здесь только окно, из которого видно ход.

Задача одна. Не потому, что трудно сделать очередь, а потому что деньги тратятся
последовательно: потолок бюджета считается по факту списаний, и две параллельные
съёмки превратили бы проверку остатка в гонку. Очередь появится, когда появится
причина её иметь.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from collections import deque

# Сколько строк вывода держим в памяти. Панель показывает хвост; полный вывод
# провайдера — в терминале и в файлах проекта, дублировать его в RAM незачем.
JOURNAL_SIZE = 400

# Как часто напоминать, что стадия жива, когда она сама ничего не печатает.
# Текстовая стадия молчит до самого ответа модели — десятки минут на сценарии
# получасовой серии, — и пустой журнал в это время неотличим от зависшей
# панели: живой прогон 2026-09-09 оборвался по таймауту движка после четверти
# часа тишины, и до этого момента на экране не было ничего.
HEARTBEAT_SECONDS = 60


class TaskBusyError(RuntimeError):
    """Задача уже идёт. Вторую не запускаем — см. модульную доку."""


class TaskRunner:
    """Реестр на одну задачу: запуск, снимок состояния, отмена."""

    def __init__(self, journal_size: int = JOURNAL_SIZE,
                 heartbeat_seconds: float = HEARTBEAT_SECONDS) -> None:
        self._journal_size = journal_size
        self._heartbeat = heartbeat_seconds
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._task: dict | None = None
        self._reader: threading.Thread | None = None
        self._cancelling = False

    # --- чтение ---

    def current(self) -> dict | None:
        """Снимок текущей (или последней завершённой) задачи.

        Возвращается КОПИЯ: панель читает состояние сервера, а не владеет им.
        """
        with self._lock:
            if self._task is None:
                return None
            snap = dict(self._task)
            snap["lines"] = list(self._task["lines"])
            return snap

    # snapshot — имя из спеки; current короче и читается в коде панели лучше.
    snapshot = current

    def is_running(self) -> bool:
        with self._lock:
            return self._task is not None and self._task["status"] == "running"

    # --- запуск ---

    def start(self, cmd: list[str], meta: dict | None = None) -> dict:
        """Запустить команду. Пока идёт предыдущая — отказ, а не очередь."""
        meta = dict(meta or {})
        with self._lock:
            if self._task is not None and self._task["status"] == "running":
                raise TaskBusyError(
                    f"идёт стадия {self._task.get('stage') or '—'}: "
                    "дождись её или отмени")

            task = {
                "id": uuid.uuid4().hex[:12],
                "kind": meta.get("kind", "stage"),
                "project": meta.get("project"),
                "episode": meta.get("episode"),
                "stage": meta.get("stage"),
                "cmd": list(cmd),
                "status": "running",
                "lines": deque(maxlen=self._journal_size),
                "exit_code": None,
                "started_at": time.time(),
                "finished_at": None,
                # Когда стадия в последний раз подала голос сама. По нему
                # решается, нужна ли отметка о том, что она ещё идёт.
                "last_output": time.time(),
            }

            # stderr в тот же поток: человек читает ОДИН журнал, разделять
            # потоки ему нечем, а трейсбек провайдера — такая же часть истории,
            # как и «снято 3 из 3».
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                env=self._child_env())

            self._proc = proc
            self._task = task
            self._cancelling = False
            self._reader = threading.Thread(
                target=self._pump, args=(proc, task), daemon=True)
            self._reader.start()
            if self._heartbeat > 0:
                threading.Thread(target=self._beat, args=(task,),
                                 daemon=True).start()

            snap = dict(task)
            snap["lines"] = list(task["lines"])
            return snap

    @staticmethod
    def _child_env() -> dict:
        """Окружение дочернего процесса.

        Две переменные, обе обязательны, и обе стоили отладки.

        `PYTHONIOENCODING=utf-8`: сообщения конвейера написаны по-русски («гейт
        закрыт», «нет pending единиц»), а дочерний python на Windows пишет их в
        кодировке консоли. Панель читает поток как utf-8, и без этого человек
        видел бы в журнале ромбики вместо объяснения, почему стадия не пошла.

        `PYTHONUNBUFFERED=1`: без него вывод приходит одной пачкой в конце, и
        панель показывала бы пустой журнал всё время съёмки, а потом сразу итог.
        Прогресс, который появляется только после окончания, — не прогресс.
        """
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def _pump(self, proc: subprocess.Popen, task: dict) -> None:
        """Читать вывод до конца процесса и проставить итоговый статус."""
        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    with self._lock:
                        task["lines"].append(line.rstrip("\n"))
                        task["last_output"] = time.time()
        finally:
            code = proc.wait()
            with self._lock:
                task["exit_code"] = code
                task["finished_at"] = time.time()
                if self._cancelling:
                    task["status"] = "cancelled"
                elif code == 0:
                    task["status"] = "done"
                else:
                    # Коды выхода конвейера осмысленны: 2 — негодные входные
                    # данные, 3 — закрытый гейт. Показать их человеку важнее,
                    # чем сказать «не получилось».
                    task["status"] = "failed"

    def _beat(self, task: dict) -> None:
        """Отмечать в журнале, что молчащая стадия ещё идёт.

        Только МОЛЧАЩАЯ: стадия, которая сама печатает прогресс, в подсказках
        не нуждается, а лишние строки вытеснили бы из журнала настоящие — он
        ограничен по длине.
        """
        while True:
            time.sleep(min(self._heartbeat, 1.0))
            with self._lock:
                if task["status"] != "running":
                    return
                now = time.time()
                if now - task["last_output"] < self._heartbeat:
                    continue
                minutes = int((now - task["started_at"]) // 60)
                task["lines"].append(
                    f"— идёт {minutes} мин, стадия ещё думает" if minutes
                    else "— идёт, стадия ещё думает")
                task["last_output"] = now

    # --- отмена ---

    def cancel(self) -> bool:
        """Прервать текущую задачу. Возвращает False, если прерывать нечего."""
        with self._lock:
            if self._task is None or self._task["status"] != "running":
                return False
            proc, task = self._proc, self._task
            self._cancelling = True
            task["lines"].append("— прервано человеком из панели")

        if proc is not None:
            proc.terminate()
        return True
