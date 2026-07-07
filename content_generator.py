"""
content_generator.py — Pipeline pembuatan konten HR.

Alur:
1. Ambil topik hari ini (rotasi dari topics.json, hindari topik yang baru dipakai)
2. Cari berita/tren HR terkini via Tavily API
3. Generate konten human-like via Gemini atau Claude API
"""

import json
import random
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path

from tavily import TavilyClient

import config

logger = logging.getLogger(__name__)

TOPICS_PATH = Path(__file__).parent / "topics.json"
DB_PATH = Path(__file__).parent / "content_log.db"

# ── Inisialisasi Database ────────────────────────────────────────────────────

def init_db():
    """Buat tabel log jika belum ada."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS content_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            topic       TEXT NOT NULL,
            category    TEXT NOT NULL,
            draft       TEXT NOT NULL,
            final       TEXT,
            status      TEXT NOT NULL DEFAULT 'pending',
            created_at  TEXT NOT NULL,
            published_at TEXT
        )
    """)
    conn.commit()
    conn.close()


# ── Pemilihan Topik ──────────────────────────────────────────────────────────

def _get_recent_topics(days: int = 30) -> list[str]:
    """Ambil topik yang sudah dipakai dalam N hari terakhir."""
    conn = sqlite3.connect(DB_PATH)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT topic FROM content_log WHERE date >= ?", (cutoff,)
    ).fetchall()
    conn.close()
    return [row[0] for row in rows]


def pick_topic() -> tuple[str, str]:
    """
    Pilih satu topik secara acak dari topics.json,
    menghindari topik yang sudah dipakai dalam 30 hari terakhir.
    Mengembalikan (topik, kategori).
    """
    with open(TOPICS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    recent = set(_get_recent_topics())

    all_topics: list[tuple[str, str]] = []
    for cat in data["topics"]:
        for item in cat["items"]:
            if item not in recent:
                all_topics.append((item, cat["category"]))

    # Jika semua topik sudah pernah dipakai, reset dan ambil semua
    if not all_topics:
        logger.warning("Semua topik sudah pernah dipakai. Mereset rotasi.")
        for cat in data["topics"]:
            for item in cat["items"]:
                all_topics.append((item, cat["category"]))

    return random.choice(all_topics)


# ── Web Search (Tavily) ──────────────────────────────────────────────────────

def search_hr_news(topic: str) -> str:
    """
    Cari berita/tren HR terkini yang relevan dengan topik.
    Mengembalikan string ringkasan hasil pencarian.
    """
    try:
        client = TavilyClient(api_key=config.TAVILY_API_KEY)
        query = f"HR human resources {topic} Indonesia 2024 2025 terkini"
        results = client.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_answer=True
        )

        snippets = []
        if results.get("answer"):
            snippets.append(f"Ringkasan: {results['answer']}")
        for r in results.get("results", []):
            if r.get("content"):
                snippets.append(f"- {r['content'][:300]}")

        return "\n".join(snippets) if snippets else ""

    except Exception as e:
        logger.warning(f"Tavily search gagal: {e}. Melanjutkan tanpa berita terkini.")
        return ""


# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Kamu adalah seorang HR profesional berpengalaman di Indonesia yang aktif berbagi insight di media sosial Threads.

Tugas kamu adalah menulis satu konten Threads berdasarkan topik dan informasi yang diberikan.

CONTOH GAYA BAHASA DAN PENULISAN ASLI (TIRU GAYA INI):
\"\"\"
Saya baru saja membaca 5 stages of leadership. Saya coba share di sini. Menjadi Supervisor, Manager, atau Head memang membuat Anda memiliki wewenang. Tapi wewenang tidak otomatis membuat orang percaya, menghormati, atau terinspirasi untuk mengikuti Anda.

John C. Maxwell menyebut perjalanan ini sebagai 5 Levels of Leadership. Menariknya, hampir semua leader akan melewati tahapan ini. 1. Position — Orang Mengikuti Karena Harus

Ini adalah level ketika jabatan menjadi sumber pengaruh. Contohnya sederhana. Seorang supervisor baru masuk ke sebuah perusahaan manufaktur. Di hari pertama ia berkata, "Mulai besok semua laporan harus masuk sebelum jam 5 sore."

Tim mengerjakannya. Bukan karena mereka percaya pada supervisornya. Tapi karena dia adalah atasan mereka. Di level ini, kepatuhan masih bergantung pada struktur organisasi. Masalahnya, ketika supervisor sedang cuti, laporan mulai terlambat lagi. Artinya, yang dihormati bukan kepemimpinannya, melainkan jabatannya. 3. Production — Orang Mengikuti Karena Ada Hasil Nyata

Sekarang bayangkan ada dua manager. Manager pertama sangat ramah. Manager kedua juga ramah, tetapi berhasil memangkas waktu pengerjaan proyek dari 30 hari menjadi 18 hari tanpa menambah jam lembur. Selain itu:
Turnover tim turun.
Target penjualan konsisten tercapai.
Keluhan pelanggan berkurang.
Proyek selesai tepat waktu.

Menurut Anda, manager mana yang lebih mudah mendapatkan kepercayaan dari tim dan direksi? Walaupun baru jalan bulan kedua, beliau mendapatkan benefit yang dirasa cocok dan sejalan dengan value beliau. Sebenarnya tim yang beliau miliki, secara hasil survey sudah bagus dan engage semua di segala aspek. 
Namun beliau merasa masih ada yang harus diimprove dari tim, serta pengembangan bisnis.
\"\"\"

ATURAN GAYA PENULISAN (WAJIB DIIKUTI):
1. Tulis seperti manusia biasa (human-like), BUKAN seperti AI. Tiru persis gaya penuturan, penggunaan diksi (seperti "beliau", "Anda", "tim", "improve", "engage"), dan pola kalimat dari contoh di atas.
2. Gunakan storytelling (bercerita) dengan memberikan studi kasus atau perumpamaan konkret seperti contoh di atas.
3. Gunakan kalimat pendek yang nyaman dibaca.
4. Gunakan kata ganti "Saya", "Anda", "Beliau", "Mereka". Gaya bahasanya profesional tapi tetap luwes dan bercerita.
5. Jangan menggunakan pembuka atau penutup yang terlalu kaku khas AI (seperti "Kesimpulannya..").
6. Penutup harus mengundang refleksi berupa pertanyaan tajam ke pembaca atau insight berharga.
7. Panjang konten: 150–500 kata. Boleh panjang karena sistem akan otomatis memecahnya menjadi rangkaian thread. Tulis mengalir, jangan potong sendiri.
8. Akhiri dengan maksimal 4 hashtag yang relevan.
9. Informasi yang ditulis harus FAKTUAL dan logis.

FORMAT OUTPUT:
Langsung tulis kontennya saja. Tanpa judul, tanpa label, tanpa pembuka seperti "Berikut kontennya:".
"""


# ── AI Content Generation ────────────────────────────────────────────────────

def _generate_with_gemini(topic: str, category: str, news_context: str) -> str:
    """Generate konten menggunakan Google Gemini API."""
    import google.generativeai as genai

    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=SYSTEM_PROMPT
    )

    user_prompt = _build_user_prompt(topic, category, news_context)
    response = model.generate_content(user_prompt)
    return response.text.strip()


def _generate_with_claude(topic: str, category: str, news_context: str) -> str:
    """Generate konten menggunakan Anthropic Claude API."""
    import anthropic

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    user_prompt = _build_user_prompt(topic, category, news_context)

    message = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return message.content[0].text.strip()


def _build_user_prompt(topic: str, category: str, news_context: str) -> str:
    """Susun prompt untuk AI berdasarkan topik dan konteks berita."""
    context_section = ""
    if news_context:
        context_section = f"""
KONTEKS BERITA/TREN TERKINI (gunakan sebagai referensi faktual jika relevan):
{news_context}
"""
    return f"""Topik: {topic}
Kategori: {category}
{context_section}
Tulis konten Threads sesuai aturan yang sudah ditetapkan."""


# ── Main Pipeline ────────────────────────────────────────────────────────────

def generate_content() -> dict:
    """
    Pipeline utama: pilih topik → cari berita → generate konten.
    Mengembalikan dict berisi topik, kategori, dan draft konten.
    """
    init_db()

    topic, category = pick_topic()
    logger.info(f"Topik terpilih: [{category}] {topic}")

    news_context = search_hr_news(topic)
    if news_context:
        logger.info("Konteks berita berhasil didapat dari Tavily.")
    else:
        logger.info("Tidak ada konteks berita, generate dari pengetahuan AI saja.")

    # Generate konten sesuai provider yang dikonfigurasi
    if config.AI_PROVIDER == "claude":
        draft = _generate_with_claude(topic, category, news_context)
    else:
        draft = _generate_with_gemini(topic, category, news_context)

    logger.info("Draft konten berhasil digenerate.")

    # Simpan ke database dengan status 'pending'
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO content_log (date, topic, category, draft, status, created_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
    """, (today, topic, category, draft, datetime.now().isoformat()))
    conn.commit()
    last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    return {
        "id": last_id,
        "topic": topic,
        "category": category,
        "draft": draft
    }


def update_content_status(content_id: int, status: str, final_text: str = None):
    """Update status konten di database (approved/edited/skipped)."""
    conn = sqlite3.connect(DB_PATH)
    if status == "published" and final_text:
        conn.execute("""
            UPDATE content_log
            SET status = ?, final = ?, published_at = ?
            WHERE id = ?
        """, (status, final_text, datetime.now().isoformat(), content_id))
    else:
        conn.execute(
            "UPDATE content_log SET status = ? WHERE id = ?",
            (status, content_id)
        )
    conn.commit()
    conn.close()
