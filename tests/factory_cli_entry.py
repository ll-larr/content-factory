"""Импорт scripts/factory.py под именем, не конфликтующим с пакетом factory."""
import importlib.util
from pathlib import Path

_path = Path(__file__).resolve().parents[1] / "scripts" / "factory.py"
_spec = importlib.util.spec_from_file_location("factory_cli", _path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

main = _mod.main

# Сам модуль — чтобы тесты могли подменять его внутренние функции.
__all__ = ["main", "_mod"]
