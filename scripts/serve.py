"""Панель управления конвейером: локальный веб-интерфейс.

Запускать из корня репозитория:
  python scripts/serve.py                 # http://127.0.0.1:8765
  python scripts/serve.py --port 9000

Тонкая обёртка над `factory.webapp`: маршрутизация, JSON и отдача файлов.
Вся логика — там, поэтому здесь нечего тестировать отдельно.

Сервер слушает ТОЛЬКО 127.0.0.1 и не имеет аутентификации: он даёт полный
доступ к проектам и запускает трату денег. В сеть его выставлять нельзя, и
адрес привязки намеренно не сделан настраиваемым — флаг `--host` появился бы в
чьей-нибудь команде раньше, чем к нему появился бы пароль.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from factory import environment, webapp                                    # noqa: E402
from factory.env import load_env                              # noqa: E402
from factory.tasks import TaskRunner                          # noqa: E402
from factory.webapp import WebappError                        # noqa: E402

HOST = "127.0.0.1"
PROJECTS_ROOT = Path("projects")
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"

# Один реестр задач на сервер: задача принадлежит ему, а не вкладке браузера.
RUNNER = TaskRunner()


class Handler(BaseHTTPRequestHandler):
    server_version = "content-factory-panel"

    # --- ответы ---
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # Панель отдаёт файлы проекта и собственный HTML. Ни то, ни другое не
        # должно исполняться как чужой скрипт и вставляться в чужую страницу.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; media-src 'self'; img-src 'self' data:")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code: int = 200) -> None:
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, code: int, message: str) -> None:
        self._json({"error": message}, code)

    # --- маршруты ---
    def do_GET(self) -> None:                       # noqa: N802 (имя из stdlib)
        url = urlparse(self.path)
        path = unquote(url.path)
        try:
            if path in ("/", "/index.html"):
                return self._file(WEB_DIR / "index.html")
            # Статика панели: строго перечисленные файлы, а не любой путь под
            # WEB_DIR. Список короткий, и перечислить его дешевле, чем городить
            # ещё одну проверку выхода за каталог.
            if path.lstrip("/") in ("app.css", "app.js", "favicon.svg"):
                return self._file(WEB_DIR / path.lstrip("/"))
            # Браузер просит /favicon.ico сам, без ссылки в разметке, и 404 на
            # него сыпался в консоль при каждой загрузке панели.
            if path == "/favicon.ico":
                return self._file(WEB_DIR / "favicon.svg")
            if path == "/api/projects":
                return self._json({"projects": webapp.list_projects(PROJECTS_ROOT)})
            if path.startswith("/api/project/"):
                name = path[len("/api/project/"):]
                return self._json(
                    webapp.project_overview(self._project_dir(name)))
            if path == "/api/task":
                return self._json({"task": RUNNER.current()})
            if path == "/api/keys":
                return self._json({"keys": webapp.keys_state(ROOT)})
            if path == "/api/text":
                q = parse_qs(url.query)
                name = (q.get("project") or [""])[0]
                return self._json({
                    "stages": webapp.text_stages(self._project_dir(name)),
                    **webapp.text_engines()})
            if path == "/api/models":
                q = parse_qs(url.query)
                name = (q.get("project") or [""])[0]
                return self._json({"roles": webapp.model_roles(
                    self._project_dir(name))})
            if path == "/api/environment":
                return self._json({"tools": webapp.environment_state()})
            if path == "/api/mixer":
                q = parse_qs(url.query)
                name = (q.get("project") or [""])[0]
                return self._json(webapp.mixer(self._project_dir(name)))
            if path == "/api/new":
                return self._json(webapp.new_project_options())
            if path == "/api/voices":
                q = parse_qs(url.query)
                return self._json(webapp.voice_catalog(
                    (q.get("language") or ["ru"])[0]))
            if path.startswith("/voice-sample/"):
                # <модель>/<язык>/<пресет>.mp3 — три имени из URL, каждое
                # проверяется как имя файла (webapp.voice_sample_file).
                parts = path[len("/voice-sample/"):].split("/")
                if len(parts) != 3:
                    return self._error(404, f"нет маршрута {path}")
                model, language, name = parts
                return self._file(webapp.voice_sample_file(
                    model, language, name.removesuffix(".mp3")))
            if path == "/api/balances":
                return self._json({"balances": webapp.balances()})
            if path == "/api/estimate":
                q = parse_qs(url.query)
                name = (q.get("project") or [""])[0]
                episode = (q.get("episode") or [""])[0]
                return self._json(webapp.episode_estimate(
                    self._project_dir(name), episode))
            if path.startswith("/media/"):
                rest = path[len("/media/"):]
                name, _, rel = rest.partition("/")
                return self._file(
                    webapp.media_path(self._project_dir(name), rel))
        except WebappError as e:
            return self._error(400, str(e))
        except OSError as e:
            return self._error(404, str(e))
        self._error(404, f"нет маршрута {path}")

    def do_POST(self) -> None:                      # noqa: N802
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return self._error(400, "тело запроса не разбирается как JSON")
        try:
            if url.path == "/api/review":
                item = webapp.review_action(
                    self._project_dir(payload.get("project", "")),
                    payload.get("item", ""), payload.get("action", ""),
                    payload.get("reason"))
                return self._json({"item": item})
            if url.path == "/api/approve":
                return self._json(webapp.approve_artifact(
                    self._project_dir(payload.get("project", "")),
                    payload.get("path", "")))
            if url.path == "/api/run":
                try:
                    task = webapp.run_stage(
                        RUNNER, PROJECTS_ROOT, payload.get("project", ""),
                        payload.get("episode", ""), payload.get("stage", ""))
                except WebappError as e:
                    # Занятый реестр — не ошибка запроса: человек не сделал
                    # ничего плохого, просто ещё идёт оплаченная съёмка.
                    if RUNNER.is_running():
                        return self._error(409, str(e))
                    raise
                return self._json({"task": task})
            if url.path == "/api/cancel":
                return self._json({"cancelled": RUNNER.cancel(),
                                   "task": RUNNER.current()})
            if url.path == "/api/text":
                # Текстовая стадия — та же долгая задача, что и съёмка: модель
                # думает минутами, и вкладка не должна её держать.
                try:
                    task = webapp.run_text_task(
                        RUNNER, PROJECTS_ROOT, payload.get("project", ""),
                        payload.get("stage", ""),
                        request=payload.get("request", ""),
                        episode=payload.get("episode") or None,
                        model=payload.get("model") or None,
                        engine=payload.get("engine") or None,
                        repo_root=ROOT)
                except WebappError as e:
                    if RUNNER.is_running():
                        return self._error(409, str(e))
                    raise
                return self._json({"task": task})
            if url.path == "/api/new":
                return self._json(webapp.create_project(PROJECTS_ROOT, payload))
            if url.path == "/api/voices":
                try:
                    task = webapp.run_voice_samples(
                        RUNNER, payload.get("language") or "ru",
                        payload.get("model") or webapp.VOICE_MODEL,
                        voices_wanted=payload.get("voices") or None)
                except WebappError as e:
                    if RUNNER.is_running():
                        return self._error(409, str(e))
                    raise
                return self._json({"task": task})
            if url.path == "/api/models":
                return self._json(webapp.set_project_models(
                    self._project_dir(payload.get("project", "")),
                    payload.get("models") or {}))
            if url.path == "/api/mixer":
                return self._json(webapp.set_mixer(
                    self._project_dir(payload.get("project", "")),
                    {k: v for k, v in payload.items()
                     if k in ("volumes", "muted", "speakers", "duck",
                              "target_lufs")}))
            if url.path == "/api/settings":
                return self._json(webapp.set_project_settings(
                    self._project_dir(payload.get("project", "")),
                    {k: v for k, v in payload.items()
                     if k in ("language", "visual_mode")}))
            if url.path == "/api/keys":
                return self._json({"key": webapp.set_key(
                    ROOT, payload.get("provider", ""), payload.get("value", ""))})
        except WebappError as e:
            return self._error(400, str(e))
        self._error(404, f"нет маршрута {url.path}")

    # --- вспомогательное ---
    def _project_dir(self, name: str) -> Path:
        """Каталог проекта по имени из запроса.

        Имя приходит из URL, поэтому проверяется как имя файла: без этого
        `/api/project/../../` читал бы что угодно (тот же класс ошибки, что
        закрыт в audio.json и shots.json ревью безопасности 2026-09-05).
        """
        from factory.safety import is_safe_name
        if not is_safe_name(name):
            raise WebappError(f"негодное имя проекта: {name!r}")
        directory = PROJECTS_ROOT / name
        if not (directory / "project.json").exists():
            raise WebappError(f"нет проекта {name!r}")
        return directory

    def _file(self, path: Path) -> None:
        data = Path(path).read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("+xml"):
            ctype += "; charset=utf-8"
        self._send(200, data, ctype)

    def log_message(self, fmt, *args):
        """Тише stdlib: одна строка на запрос вместо шапки с датой."""
        sys.stderr.write(f"  {self.command} {self.path}\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true",
                    help="не открывать браузер автоматически")
    args = ap.parse_args(argv)
    # Ключи из .env рядом с корнем: на чужой машине это единственный способ
    # задать их, не воюя с системными переменными окружения.
    load_env(Path(__file__).resolve().parent.parent)

    if not WEB_DIR.exists():
        print(f"нет каталога {WEB_DIR} — панель не собрана")
        return 1

    # Чего не хватает на машине — сразу, в окне лаунчера. Панель показывает то
    # же самое баннером, но человек, запустивший её двойным кликом, смотрит
    # именно сюда, и узнать про отсутствующий ffmpeg лучше до съёмки, а не
    # трейсбеком после неё. Это не отказ: ревью кадров работает и без ffmpeg.
    blockers = environment.problems(ROOT)
    if blockers:
        print("Не всё установлено — часть конвейера работать не будет:")
        for line in blockers:
            print(f"  - {line}")
        print()

    server = ThreadingHTTPServer((HOST, args.port), Handler)
    url = f"http://{HOST}:{args.port}/"
    print(f"Панель: {url}   (Ctrl+C — остановить)")
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
