"""
schedule_manager.py — Manajemen jadwal posting via database SQLite.

Menyimpan jadwal di database agar bisa diubah runtime tanpa restart server.
HR client bisa menambah/hapus jadwal via command Telegram.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
import os

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
DB_PATH = DATA_DIR / "content_log.db"


def init_schedule_db() -> None:
    """Buat tabel schedules jika belum ada."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            time        TEXT NOT NULL UNIQUE,
            created_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Tabel schedules diinisialisasi.")


def get_schedules() -> list[str]:
    """
    Ambil semua jadwal aktif, diurutkan dari yang paling awal.
    Mengembalikan list string format HH:MM, misalnya ["09:00", "14:30", "18:00"].
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT time FROM schedules ORDER BY time").fetchall()
    conn.close()
    return [row[0] for row in rows]


def add_schedule(time_str: str) -> bool:
    """
    Tambah jadwal baru. Mengembalikan True jika berhasil, False jika sudah ada.
    Format time_str: "HH:MM"
    """
    # Validasi format
    try:
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        time_str = f"{hour:02d}:{minute:02d}"  # Normalisasi format
    except (ValueError, AttributeError):
        raise ValueError(f"Format waktu tidak valid: '{time_str}'. Gunakan format HH:MM (contoh: 14:30)")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT INTO schedules (time, created_at) VALUES (?, ?)",
            (time_str, datetime.now().isoformat())
        )
        conn.commit()
        logger.info(f"Jadwal baru ditambahkan: {time_str}")
        return True
    except sqlite3.IntegrityError:
        logger.warning(f"Jadwal {time_str} sudah ada.")
        return False
    finally:
        conn.close()


def remove_schedule(time_str: str) -> bool:
    """
    Hapus jadwal tertentu. Mengembalikan True jika berhasil dihapus.
    """
    # Normalisasi format
    try:
        hour, minute = map(int, time_str.split(":"))
        time_str = f"{hour:02d}:{minute:02d}"
    except (ValueError, AttributeError):
        raise ValueError(f"Format waktu tidak valid: '{time_str}'.")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("DELETE FROM schedules WHERE time = ?", (time_str,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()

    if deleted:
        logger.info(f"Jadwal {time_str} dihapus.")
    else:
        logger.warning(f"Jadwal {time_str} tidak ditemukan.")

    return deleted


def clear_schedules() -> int:
    """Hapus semua jadwal. Mengembalikan jumlah jadwal yang dihapus."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("DELETE FROM schedules")
    conn.commit()
    count = cursor.rowcount
    conn.close()
    logger.info(f"Semua jadwal dihapus ({count} jadwal).")
    return count


def seed_default_schedule(default_time: str) -> None:
    """
    Jika belum ada jadwal di database, masukkan jadwal default dari .env.
    Dipanggil saat startup.
    """
    schedules = get_schedules()
    if not schedules:
        try:
            add_schedule(default_time)
            logger.info(f"Jadwal default dari .env ditambahkan: {default_time}")
        except ValueError as e:
            logger.error(f"Gagal menambahkan jadwal default: {e}")
