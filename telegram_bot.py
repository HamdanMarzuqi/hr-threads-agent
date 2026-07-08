"""
telegram_bot.py — Review gate konten via Telegram Bot.

Alur:
1. Kirim draft konten ke HR via Telegram
2. HR membalas salah satu:
   /approve → upload ke Threads
   /edit [teks baru] → upload teks yang sudah diedit
   /skip → batalkan upload hari ini
3. Jika tidak ada respons:
   - Setelah REVIEW_REMINDER_MINUTES → kirim pengingat
   - Setelah REVIEW_SKIP_MINUTES → auto-skip
"""

import asyncio
import logging
from datetime import datetime

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

import config
from content_generator import update_content_status
from threads_publisher import publish_to_threads
import schedule_manager

logger = logging.getLogger(__name__)

# Callbacks to avoid circular imports with main.py
_generate_callback = None
_reload_scheduler_callback = None

def set_callbacks(generate_cb, reload_cb):
    global _generate_callback, _reload_scheduler_callback
    _generate_callback = generate_cb
    _reload_scheduler_callback = reload_cb

# State sederhana untuk menyimpan konten yang sedang menunggu review
# Format: { content_id: { "draft": str, "topic": str } }
_pending_content: dict[int, dict] = {}


def _escape_md(text: str) -> str:
    """Escape karakter khusus Markdown agar aman dikirim ke Telegram."""
    for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = text.replace(char, f'\\{char}')
    return text


# ── Helper ───────────────────────────────────────────────────────────────────

async def send_draft_for_review(content: dict) -> None:
    """
    Kirim draft konten ke HR via Telegram untuk direview.
    Menyimpan state pending dan set timer pengingat + auto-skip.

    PENTING: Selalu clear semua konten pending sebelumnya agar
    /approve selalu mengambil konten yang paling baru di-generate.
    """
    content_id = content["id"]
    draft = content["draft"]
    topic = content["topic"]
    category = content["category"]

    # Clear semua konten pending sebelumnya agar /approve selalu
    # mengambil konten terbaru, bukan konten lama.
    if _pending_content:
        old_ids = list(_pending_content.keys())
        logger.info(f"Menghapus {len(old_ids)} konten pending lama: {old_ids}")
        _pending_content.clear()

    _pending_content[content_id] = {
        "draft": draft,
        "topic": topic,
        "category": category
    }
    logger.info(f"Konten baru (ID: {content_id}) disimpan sebagai pending. Total pending: {len(_pending_content)}")

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)

    # Kirim header dulu
    header = (
        f"📝 *Draft Konten HR — {datetime.now().strftime('%d %b %Y')}*\n"
        f"📂 Kategori: {category}\n"
        f"💡 Topik: {topic}\n\n"
        f"{'─' * 30}"
    )
    await bot.send_message(
        chat_id=config.TELEGRAM_CHAT_ID,
        text=header,
        parse_mode=ParseMode.MARKDOWN
    )

    # Kirim draft sebagai plain text (tanpa Markdown) agar tidak error parsing
    await bot.send_message(
        chat_id=config.TELEGRAM_CHAT_ID,
        text=draft
    )

    # Kirim instruksi
    footer = (
        f"{'─' * 30}\n\n"
        f"Balas dengan:\n"
        f"✅ /approve — Upload sekarang\n"
        f"✏️ /edit \\[teks baru\\] — Ganti konten lalu upload\n"
        f"⏭️ /skip — Lewati hari ini\n\n"
        f"⏰ Pengingat dalam {config.REVIEW_REMINDER_MINUTES} menit jika belum ada respons."
    )
    await bot.send_message(
        chat_id=config.TELEGRAM_CHAT_ID,
        text=footer,
        parse_mode=ParseMode.MARKDOWN
    )

    # Simpan content_id di bot_data untuk digunakan command handler
    # (akan diakses via application.bot_data)
    logger.info(f"Draft konten (ID: {content_id}) dikirim ke Telegram HR.")


async def send_notification(text: str) -> None:
    """Kirim notifikasi sederhana ke HR via Telegram."""
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    await bot.send_message(
        chat_id=config.TELEGRAM_CHAT_ID,
        text=text,
        parse_mode=ParseMode.MARKDOWN
    )


# ── Command Handlers ─────────────────────────────────────────────────────────

async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /approve — upload draft konten yang sedang pending."""
    if update.effective_chat.id != config.TELEGRAM_CHAT_ID:
        return

    if not _pending_content:
        await update.message.reply_text("ℹ️ Tidak ada konten yang sedang menunggu review.")
        return

    # Ambil konten pending pertama (biasanya hanya ada 1)
    content_id, content_data = next(iter(_pending_content.items()))
    draft = content_data["draft"]

    await update.message.reply_text("⏳ Sedang mengupload ke Threads...")

    try:
        post_id = publish_to_threads(draft)
        update_content_status(content_id, "published", draft)
        _pending_content.pop(content_id, None)

        await update.message.reply_text(
            f"✅ Konten berhasil diupload ke Threads!\n\n"
            f"🔗 Post ID: {post_id}\n\n"
            f"Preview konten:\n{draft[:200]}..."
        )
        logger.info(f"Konten ID {content_id} berhasil dipublish. Post ID: {post_id}")

    except Exception as e:
        logger.error(f"Gagal upload ke Threads: {e}")
        await update.message.reply_text(
            f"❌ *Gagal upload ke Threads.*\n\nError: `{e}`\n\n"
            f"Silakan coba /approve lagi atau hubungi developer.",
            parse_mode=ParseMode.MARKDOWN
        )


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /edit [teks baru] — ganti konten dengan teks dari HR lalu upload."""
    if update.effective_chat.id != config.TELEGRAM_CHAT_ID:
        return

    if not _pending_content:
        await update.message.reply_text("ℹ️ Tidak ada konten yang sedang menunggu review.")
        return

    # Ambil teks setelah command /edit
    new_text = " ".join(context.args) if context.args else ""
    if not new_text:
        await update.message.reply_text(
            "⚠️ Format: `/edit [teks konten baru kamu di sini]`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    content_id, _ = next(iter(_pending_content.items()))

    await update.message.reply_text("⏳ Sedang mengupload versi yang sudah diedit ke Threads...")

    try:
        post_id = publish_to_threads(new_text)
        update_content_status(content_id, "published", new_text)
        _pending_content.pop(content_id, None)

        await update.message.reply_text(
            f"✅ *Konten (versi editanmu) berhasil diupload ke Threads!*\n\n"
            f"🔗 Post ID: `{post_id}`",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info(f"Konten ID {content_id} (edited) berhasil dipublish.")

    except Exception as e:
        logger.error(f"Gagal upload konten yang diedit: {e}")
        await update.message.reply_text(
            f"❌ *Gagal upload ke Threads.*\n\nError: `{e}`",
            parse_mode=ParseMode.MARKDOWN
        )


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /skip — batalkan upload konten hari ini."""
    if update.effective_chat.id != config.TELEGRAM_CHAT_ID:
        return

    if not _pending_content:
        await update.message.reply_text("ℹ️ Tidak ada konten yang sedang menunggu review.")
        return

    content_id, _ = next(iter(_pending_content.items()))
    update_content_status(content_id, "skipped")
    _pending_content.pop(content_id, None)

    await update.message.reply_text(
        "⏭️ Konten hari ini dilewati. Sampai besok!"
    )
    logger.info(f"Konten ID {content_id} di-skip oleh HR.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /status — cek apakah ada konten yang sedang pending review."""
    if update.effective_chat.id != config.TELEGRAM_CHAT_ID:
        return

    if _pending_content:
        content_id, data = next(iter(_pending_content.items()))
        await update.message.reply_text(
            f"📋 Ada 1 konten sedang menunggu review (ID: {content_id})\n"
            f"Topik: {data['topic']}\n\n"
            f"Gunakan /approve, /edit, atau /skip."
        )
    else:
        await update.message.reply_text("✅ Tidak ada konten yang menunggu review saat ini.")


async def cmd_jadwal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /jadwal — lihat semua jadwal aktif."""
    if update.effective_chat.id != config.TELEGRAM_CHAT_ID:
        return

    schedules = schedule_manager.get_schedules()
    if not schedules:
        await update.message.reply_text("📅 Saat ini tidak ada jadwal posting yang aktif.")
        return

    text = "📅 *Jadwal Posting Aktif (WIB):*\n\n"
    for i, s in enumerate(schedules, 1):
        text += f"{i}. {s}\n"
    text += f"\nTotal: {len(schedules)} posting/hari"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_setjadwal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /setjadwal HH:MM — tambah jadwal baru."""
    if update.effective_chat.id != config.TELEGRAM_CHAT_ID:
        return

    if not context.args:
        await update.message.reply_text("⚠️ Format: `/setjadwal HH:MM` (contoh: `/setjadwal 09:00`)", parse_mode=ParseMode.MARKDOWN)
        return

    time_str = context.args[0]
    try:
        added = schedule_manager.add_schedule(time_str)
        if added:
            if _reload_scheduler_callback:
                _reload_scheduler_callback()
            
            schedules = schedule_manager.get_schedules()
            text = f"✅ Jadwal baru ditambahkan: *{time_str} WIB*\n\nJadwal aktif:\n"
            text += ", ".join(schedules)
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"⚠️ Jadwal {time_str} sudah ada.")
    except ValueError as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_hapusjadwal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /hapusjadwal HH:MM — hapus jadwal."""
    if update.effective_chat.id != config.TELEGRAM_CHAT_ID:
        return

    if not context.args:
        await update.message.reply_text("⚠️ Format: `/hapusjadwal HH:MM` (contoh: `/hapusjadwal 09:00`)", parse_mode=ParseMode.MARKDOWN)
        return

    time_str = context.args[0]
    try:
        removed = schedule_manager.remove_schedule(time_str)
        if removed:
            if _reload_scheduler_callback:
                _reload_scheduler_callback()
            
            schedules = schedule_manager.get_schedules()
            text = f"✅ Jadwal dihapus: *{time_str} WIB*\n\n"
            if schedules:
                text += "Jadwal tersisa: " + ", ".join(schedules)
            else:
                text += "⚠️ Tidak ada jadwal tersisa. Gunakan /setjadwal untuk menambah."
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(f"⚠️ Jadwal {time_str} tidak ditemukan.")
    except ValueError as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cmd_generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /generate — trigger pembuatan konten sekarang juga."""
    if update.effective_chat.id != config.TELEGRAM_CHAT_ID:
        return

    await update.message.reply_text("⏳ Sedang men-generate draft konten. Mohon tunggu sekitar 1-2 menit...")
    
    if _generate_callback:
        # PENTING: Await callback agar generate selesai sepenuhnya dan
        # konten baru tersimpan di _pending_content SEBELUM user bisa /approve.
        # Sebelumnya menggunakan create_task() (fire-and-forget) yang menyebabkan
        # race condition: /approve bisa dijalankan sebelum konten baru siap,
        # sehingga mengambil konten lama.
        try:
            await _generate_callback()
        except Exception as e:
            logger.error(f"Generate via /generate gagal: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ Gagal men-generate konten: `{e}`",
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        await update.message.reply_text("❌ Callback generator belum diset.")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler /help — tampilkan daftar command."""
    if update.effective_chat.id != config.TELEGRAM_CHAT_ID:
        return

    help_text = (
        "🤖 *HR Threads Agent — Bantuan*\n\n"
        "*Review Konten:*\n"
        "✅ `/approve` — Upload draft pending ke Threads\n"
        "✏️ `/edit [teks]` — Edit lalu upload\n"
        "⏭️ `/skip` — Batalkan upload\n"
        "📋 `/status` — Cek status review\n\n"
        "*Manajemen Jadwal:*\n"
        "📅 `/jadwal` — Lihat daftar jadwal posting otomatis\n"
        "➕ `/setjadwal HH:MM` — Tambah jadwal (WIB)\n"
        "➖ `/hapusjadwal HH:MM` — Hapus jadwal\n\n"
        "*Manual:*\n"
        "⚡ `/generate` — Buat draft konten baru secara paksa saat ini juga"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


# ── Reminder & Auto-skip Timer ───────────────────────────────────────────────

async def _run_reminder_and_autoskip(content_id: int) -> None:
    """
    Coroutine yang berjalan setelah draft dikirim:
    - Kirim pengingat setelah REVIEW_REMINDER_MINUTES menit
    - Auto-skip setelah REVIEW_SKIP_MINUTES menit
    """
    # Tunggu hingga waktunya kirim pengingat
    await asyncio.sleep(config.REVIEW_REMINDER_MINUTES * 60)

    if content_id not in _pending_content:
        return  # Sudah direview, tidak perlu pengingat

    await send_notification(
        f"⏰ *Pengingat:* Draft konten HR hari ini belum direview!\n\n"
        f"Kamu punya {config.REVIEW_SKIP_MINUTES - config.REVIEW_REMINDER_MINUTES} menit lagi "
        f"sebelum konten otomatis dilewati.\n\n"
        f"Balas dengan /approve, /edit, atau /skip."
    )
    logger.info(f"Pengingat review dikirim untuk konten ID {content_id}.")

    # Tunggu sisa waktu sebelum auto-skip
    remaining = config.REVIEW_SKIP_MINUTES - config.REVIEW_REMINDER_MINUTES
    await asyncio.sleep(remaining * 60)

    if content_id not in _pending_content:
        return  # Sudah direview setelah pengingat

    # Auto-skip
    update_content_status(content_id, "skipped_timeout")
    _pending_content.pop(content_id, None)

    await send_notification(
        "⏭️ Konten hari ini otomatis dilewati karena tidak ada respons "
        f"dalam {config.REVIEW_SKIP_MINUTES} menit. Sampai besok!"
    )
    logger.info(f"Konten ID {content_id} auto-skip karena timeout.")


def schedule_reminder(content_id: int) -> None:
    """Jalankan reminder & auto-skip timer sebagai background task asyncio."""
    asyncio.create_task(_run_reminder_and_autoskip(content_id))


# ── Bot Runner ───────────────────────────────────────────────────────────────

def build_application() -> Application:
    """Buat dan konfigurasi Telegram Application."""
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("edit", cmd_edit))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("status", cmd_status))
    
    app.add_handler(CommandHandler("jadwal", cmd_jadwal))
    app.add_handler(CommandHandler("setjadwal", cmd_setjadwal))
    app.add_handler(CommandHandler("hapusjadwal", cmd_hapusjadwal))
    app.add_handler(CommandHandler("generate", cmd_generate))
    app.add_handler(CommandHandler("help", cmd_help))

    return app
