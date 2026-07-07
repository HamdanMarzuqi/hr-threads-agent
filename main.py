"""
main.py — Entry point HR Threads Agent.

Menjalankan:
1. Validasi konfigurasi .env
2. Inisialisasi database
3. Scheduler: trigger generate + kirim ke Telegram setiap hari di jam yang ditentukan
4. Telegram Bot: mendengarkan command HR (approve/edit/skip)
"""

import asyncio
import logging
import sys
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from content_generator import generate_content, init_db
from telegram_bot import (
    build_application,
    send_draft_for_review,
    send_notification,
    schedule_reminder,
    set_callbacks
)
import schedule_manager

# ── Logging Setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("agent.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


# ── Daily Job ────────────────────────────────────────────────────────────────

async def daily_content_job() -> None:
    """
    Pekerjaan harian yang dijalankan oleh scheduler:
    1. Generate konten HR
    2. Kirim draft ke Telegram HR untuk direview
    3. Set timer pengingat & auto-skip
    """
    logger.info(f"=== Daily job dimulai: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    try:
        # Step 1: Generate konten
        logger.info("Generating konten HR...")
        content = generate_content()
        logger.info(f"Konten berhasil digenerate. ID: {content['id']}, Topik: {content['topic']}")

        # Step 2: Kirim ke Telegram
        await send_draft_for_review(content)

        # Step 3: Set timer pengingat & auto-skip
        schedule_reminder(content["id"])

    except Exception as e:
        logger.error(f"Daily job gagal: {e}", exc_info=True)
        await send_notification(
            f"❌ *HR Agent Error*\n\n"
            f"Terjadi kesalahan saat generate konten hari ini:\n`{e}`\n\n"
            f"Silakan hubungi developer."
        )


# ── Entry Point ──────────────────────────────────────────────────────────────

async def main() -> None:
    # Validasi konfigurasi
    errors = config.validate_config()
    if errors:
        logger.error("Konfigurasi tidak lengkap:")
        for err in errors:
            logger.error(f"  ✗ {err}")
        logger.error("Salin .env.example menjadi .env dan isi semua nilai yang dibutuhkan.")
        sys.exit(1)

    logger.info("✅ Konfigurasi valid.")
    logger.info(f"   AI Provider : {config.AI_PROVIDER.upper()}")
    logger.info(f"   Upload Time : {config.UPLOAD_TIME} UTC")
    logger.info(f"   Posts/Day   : {config.POSTS_PER_DAY}")

    # Inisialisasi database jadwal
    schedule_manager.init_schedule_db()
    schedule_manager.seed_default_schedule(config.UPLOAD_TIME)
    logger.info("✅ Database jadwal diinisialisasi.")

    # Setup scheduler
    scheduler = AsyncIOScheduler()
    
    def reload_scheduler():
        """Reload semua jadwal dari database ke scheduler."""
        # Hapus semua job yang ada
        for job in scheduler.get_jobs():
            scheduler.remove_job(job.id)
            
        schedules = schedule_manager.get_schedules()
        for i, time_str in enumerate(schedules):
            try:
                hour, minute = map(int, time_str.split(":"))
                scheduler.add_job(
                    daily_content_job,
                    trigger="cron",
                    hour=hour,
                    minute=minute,
                    id=f"daily_hr_content_{i}",
                    name=f"Daily HR Content ({time_str})"
                )
            except Exception as e:
                logger.error(f"Gagal menambahkan jadwal {time_str}: {e}")
                
        logger.info(f"✅ Scheduler di-reload dengan {len(schedules)} jadwal: {', '.join(schedules)}")

    # Load jadwal pertama kali
    reload_scheduler()
    scheduler.start()

    # Register callbacks untuk telegram_bot
    set_callbacks(daily_content_job, reload_scheduler)

    # Setup & jalankan Telegram Bot
    application = build_application()

    # Kirim notifikasi startup ke HR
    from telegram import Bot
    try:
        bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
        active_schedules = schedule_manager.get_schedules()
        schedules_str = ", ".join(active_schedules) if active_schedules else "Belum ada jadwal"
        
        await bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=(
                "🤖 *HR Threads Agent aktif!*\n\n"
                f"📅 Jadwal posting aktif: *{schedules_str} WIB*\n\n"
                f"🔧 Provider AI: *{config.AI_PROVIDER.upper()}*\n\n"
                "Ketik `/help` untuk melihat daftar semua perintah, termasuk cara mengubah jadwal posting."
            ),
            parse_mode="Markdown"
        )
        logger.info("✅ Notifikasi startup dikirim ke Telegram HR.")
    except Exception as e:
        logger.warning(f"Gagal kirim notifikasi startup: {e}")

    logger.info("🚀 HR Threads Agent berjalan. Tekan Ctrl+C untuk berhenti.")

    # Jalankan bot (polling)
    async with application:
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)

        # Jaga event loop tetap berjalan
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Menerima sinyal berhenti...")
        finally:
            await application.updater.stop()
            await application.stop()
            scheduler.shutdown()
            logger.info("HR Threads Agent dihentikan.")


if __name__ == "__main__":
    asyncio.run(main())
