"""Тесты обёрток ffmpeg. ffmpeg обязателен в PATH (см. conftest)."""
from factory.ffmpeg_tools import ensure_png

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_ensure_png_converts_jpeg_saved_under_png_name(tmp_path, make_jpeg):
    """WaveSpeed отдаёт JPEG, а конвейер хранит кадр как NNN.png — чиним содержимое."""
    dest = tmp_path / "001.png"
    make_jpeg(dest)
    assert dest.read_bytes()[:2] == b"\xff\xd8"

    assert ensure_png(dest) == dest
    assert dest.read_bytes()[:8] == PNG_MAGIC


def test_ensure_png_leaves_real_png_byte_identical(tmp_path):
    """Настоящий PNG не трогаем — лишняя перекодировка запрещена."""
    dest = tmp_path / "001.png"
    original = PNG_MAGIC + b"payload-not-a-valid-png-body"
    dest.write_bytes(original)

    ensure_png(dest)
    assert dest.read_bytes() == original


def test_ensure_png_leaves_no_temp_files(tmp_path, make_jpeg):
    dest = tmp_path / "001.png"
    make_jpeg(dest)
    ensure_png(dest)
    assert [p.name for p in tmp_path.iterdir()] == ["001.png"]
