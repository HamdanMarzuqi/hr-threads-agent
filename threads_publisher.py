"""
threads_publisher.py — Publikasi konten ke Threads via Meta Graph API.

Alur posting Threads API:
1. Buat media container (POST /threads) → dapat container_id
2. Tunggu container siap (GET /threads/{id}?fields=status)
3. Publish container (POST /threads/publish) → konten tayang

Jika teks > 490 karakter, konten di-split dan dipublish sebagai
rangkaian thread (reply berantai) — mirip fitur "Add to thread".
"""

import time
import logging

import requests

import config

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.threads.net/v1.0"
MAX_CHARS = 490  # Batas aman per post (Threads limit = 500)


# ── Pemecah Teks ─────────────────────────────────────────────────────────────

def _split_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """
    Pecah teks panjang menjadi beberapa bagian, masing-masing <= max_chars.
    Pemecahan dilakukan di batas kata (spasi/newline) agar tidak memotong kata.
    """
    if len(text) <= max_chars:
        return [text]

    parts = []
    while len(text) > max_chars:
        # Cari titik potong terbaik: prioritas newline, lalu spasi
        cut = text.rfind("\n", 0, max_chars)
        if cut == -1:
            cut = text.rfind(" ", 0, max_chars)
        if cut == -1:
            cut = max_chars  # Potong paksa jika tidak ada spasi

        parts.append(text[:cut].strip())
        text = text[cut:].strip()

    if text:
        parts.append(text)

    return parts


# ── Container Management ──────────────────────────────────────────────────────

def _create_container(text: str, reply_to_id: str = None) -> str:
    """
    Buat media container di Threads API.
    Jika reply_to_id diisi, container ini akan menjadi reply dari post tersebut.
    Mengembalikan container_id.
    """
    url = f"{GRAPH_API_BASE}/{config.THREADS_USER_ID}/threads"
    payload = {
        "media_type": "TEXT",
        "text": text,
        "access_token": config.THREADS_ACCESS_TOKEN
    }
    if reply_to_id:
        payload["reply_to_id"] = reply_to_id

    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    container_id = data.get("id")
    if not container_id:
        raise ValueError(f"Gagal mendapatkan container_id. Response: {data}")

    logger.info(f"Container dibuat: {container_id}" + (f" (reply ke {reply_to_id})" if reply_to_id else ""))
    return container_id


def _wait_for_container(container_id: str, max_retries: int = 10) -> bool:
    """
    Tunggu container siap untuk dipublish.
    Meta membutuhkan waktu beberapa detik untuk memproses container.
    """
    url = f"{GRAPH_API_BASE}/{container_id}"
    params = {
        "fields": "status,error_message",
        "access_token": config.THREADS_ACCESS_TOKEN
    }

    for attempt in range(max_retries):
        time.sleep(3)
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        status = data.get("status", "")

        if status == "FINISHED":
            logger.info(f"Container siap dipublish (percobaan ke-{attempt + 1}).")
            return True
        elif status == "ERROR":
            error_msg = data.get("error_message", "Unknown error")
            raise RuntimeError(f"Container gagal diproses oleh Meta: {error_msg}")
        else:
            logger.debug(f"Container status: {status}. Menunggu...")

    raise TimeoutError(f"Container tidak siap setelah {max_retries} percobaan.")


def _publish_container(container_id: str) -> str:
    """
    Publish container yang sudah siap.
    Mengembalikan post_id konten yang sudah tayang.
    """
    url = f"{GRAPH_API_BASE}/{config.THREADS_USER_ID}/threads_publish"
    payload = {
        "creation_id": container_id,
        "access_token": config.THREADS_ACCESS_TOKEN
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    post_id = data.get("id")
    if not post_id:
        raise ValueError(f"Gagal mendapatkan post_id. Response: {data}")

    logger.info(f"Konten berhasil dipublish. Post ID: {post_id}")
    return post_id


# ── Main Publisher ────────────────────────────────────────────────────────────

def publish_to_threads(text: str) -> str:
    """
    Fungsi utama: publikasikan teks ke Threads.

    Jika teks <= 490 karakter: publish sebagai 1 post tunggal.
    Jika teks > 490 karakter: split otomatis dan publish sebagai
    rangkaian thread berantai (mirip "Add to thread").

    Mengembalikan post_id dari post pertama jika berhasil.
    """
    logger.info("Memulai proses upload ke Threads...")

    parts = _split_text(text)
    logger.info(f"Konten akan dipublish dalam {len(parts)} bagian.")

    first_post_id = None
    prev_post_id = None  # ID post sebelumnya untuk dijadikan parent reply

    for i, part in enumerate(parts):
        logger.info(f"Mempublish bagian {i + 1}/{len(parts)} ({len(part)} karakter)...")

        # Buat container (reply jika bukan bagian pertama)
        container_id = _create_container(part, reply_to_id=prev_post_id)
        _wait_for_container(container_id)
        post_id = _publish_container(container_id)

        if i == 0:
            first_post_id = post_id

        prev_post_id = post_id

        # Jeda antar post agar tidak rate-limited
        if i < len(parts) - 1:
            time.sleep(2)

    logger.info(f"Semua {len(parts)} bagian berhasil dipublish. Post utama ID: {first_post_id}")
    return first_post_id
