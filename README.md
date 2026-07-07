# HR Threads Agent 🤖

AI Agent untuk mengotomatisasi pembuatan dan publikasi konten HR di platform **Threads (Meta)**.

---

## Fitur

- ✅ Generate konten HR otomatis setiap hari (Gemini / Claude API)
- ✅ Pencarian berita/tren HR terkini via Tavily
- ✅ Gaya penulisan *human-like* (tidak terasa seperti AI)
- ✅ Review gate via Telegram sebelum konten dipublikasikan
- ✅ Upload otomatis ke Threads setelah disetujui
- ✅ Notifikasi sukses/gagal via Telegram
- ✅ Log semua konten di database SQLite
- ✅ Mudah dipindah ke klien lain (cukup ganti `.env`)

---

## Prasyarat

- Python 3.11+
- Akun & API Keys (lihat bagian Setup di bawah)

---

## Instalasi

### 1. Clone / Download Proyek

```bash
git clone https://github.com/username/hr-threads-agent.git
cd hr-threads-agent
```

### 2. Buat Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup Konfigurasi

```bash
# Salin template .env
cp .env.example .env
```

Buka file `.env` dan isi semua nilai yang dibutuhkan (lihat panduan di bawah).

---

## Panduan Mendapatkan API Keys

### 1. Gemini API Key (jika menggunakan Gemini)
1. Buka [aistudio.google.com](https://aistudio.google.com)
2. Klik **Get API Key** → **Create API Key**
3. Salin key dan isi ke `GEMINI_API_KEY` di `.env`

### 2. Claude API Key (jika menggunakan Claude)
1. Buka [console.anthropic.com](https://console.anthropic.com)
2. Masuk ke **API Keys** → **Create Key**
3. Salin key dan isi ke `CLAUDE_API_KEY` di `.env`

### 3. Tavily API Key
1. Daftar di [tavily.com](https://tavily.com)
2. Buka dashboard → salin API Key
3. Isi ke `TAVILY_API_KEY` di `.env`
> Free tier: 1.000 request/bulan (cukup untuk 1 post/hari)

### 4. Telegram Bot Token & Chat ID

**Membuat Bot:**
1. Buka Telegram, cari `@BotFather`
2. Kirim `/newbot`
3. Ikuti instruksi, masukkan nama dan username bot
4. Salin token yang diberikan ke `TELEGRAM_BOT_TOKEN` di `.env`

**Mendapatkan Chat ID:**
1. Cari `@userinfobot` di Telegram
2. Kirim `/start`
3. Salin angka **Id** yang diberikan ke `TELEGRAM_CHAT_ID` di `.env`

**Aktivasi Bot:**
- Cari bot yang baru dibuat di Telegram
- Klik **Start** agar bot bisa mengirim pesan ke kamu

### 5. Threads API (Meta)

> ⚠️ Proses ini membutuhkan beberapa hari karena perlu review dari Meta.

1. Buka [developers.facebook.com](https://developers.facebook.com)
2. Klik **My Apps** → **Create App**
3. Pilih **Business** → isi detail app
4. Di dashboard app, klik **Add Product** → pilih **Threads API**
5. Di menu **Threads API** → **User Token Generator**
6. Pilih akun Threads yang akan digunakan
7. Generate token dan salin ke `THREADS_ACCESS_TOKEN` di `.env`
8. Salin juga **User ID** ke `THREADS_USER_ID` di `.env`

---

## Konfigurasi Jadwal Upload

File `.env`:

```bash
# Format HH:MM dalam UTC (bukan WIB)
# Konversi: WIB = UTC + 7
# Contoh: ingin upload jam 07:00 WIB → tulis 00:00

UPLOAD_TIME=00:00
```

---

## Menjalankan Agent

```bash
python main.py
```

Output yang diharapkan saat startup:
```
✅ Konfigurasi valid.
   AI Provider : GEMINI
   Upload Time : 00:00 UTC
   Posts/Day   : 1
✅ Database diinisialisasi.
✅ Scheduler aktif. Job akan berjalan setiap hari pukul 00:00 UTC.
✅ Notifikasi startup dikirim ke Telegram HR.
🚀 HR Threads Agent berjalan. Tekan Ctrl+C untuk berhenti.
```

Kamu juga akan menerima pesan di Telegram bahwa agent sudah aktif.

---

## Cara Penggunaan (Flow Harian)

1. **Setiap hari di jam yang ditentukan**, agent otomatis:
   - Mencari berita HR terkini
   - Membuat draft konten
   - Mengirim draft ke Telegram kamu

2. **Kamu (HR) membalas** salah satu command:
   - `/approve` — Setujui, konten langsung diupload ke Threads
   - `/edit teks baru kamu di sini` — Ganti isi konten, lalu upload
   - `/skip` — Lewati hari ini, tidak ada yang diupload

3. **Notifikasi** akan dikirim setelah upload berhasil atau gagal.

4. **Jika tidak ada respons:**
   - 2 jam → pengingat otomatis
   - 3 jam → konten otomatis dilewati (tidak diupload)

---

## Command Telegram yang Tersedia

| Command | Fungsi |
|---|---|
| `/approve` | Setujui dan upload draft konten ke Threads |
| `/edit [teks]` | Ganti konten dengan teks baru, lalu upload |
| `/skip` | Lewati konten hari ini |
| `/status` | Cek apakah ada konten yang sedang menunggu review |

---

## Deploy ke Railway (Hosting 24/7)

1. Buat akun di [railway.app](https://railway.app)
2. Klik **New Project** → **Deploy from GitHub repo**
3. Pilih repository ini
4. Di **Variables**, tambahkan semua isi `.env` kamu
5. Di **Settings** → **Start Command**: `python main.py`
6. Deploy!

> Railway akan menjalankan agent 24/7 tanpa perlu laptop kamu menyala.

---

## Serah Terima ke Klien

Untuk memindahkan agent ke klien baru:

1. Klien membuat semua akun & API keys (lihat panduan di atas)
2. Ganti isi file `.env` dengan API keys klien
3. Ubah `TELEGRAM_CHAT_ID` ke akun Telegram klien
4. Atur ulang `UPLOAD_TIME` sesuai preferensi klien
5. Redeploy ke Railway

**Tidak ada perubahan kode yang diperlukan.**

---

## Struktur Proyek

```
hr-threads-agent/
├── main.py                 # Entry point & scheduler
├── config.py               # Load environment variables
├── content_generator.py    # Tavily + AI → generate konten
├── telegram_bot.py         # Review gate via Telegram
├── threads_publisher.py    # Meta Threads API publisher
├── topics.json             # Bank topik HR (40 topik, 8 kategori)
├── content_log.db          # SQLite log (auto-generated)
├── agent.log               # Log file (auto-generated)
├── .env                    # API keys (JANGAN di-commit!)
├── .env.example            # Template .env
├── requirements.txt
└── README.md
```

---

## Troubleshooting

| Error | Solusi |
|---|---|
| `Konfigurasi tidak lengkap` | Pastikan semua nilai di `.env` sudah diisi |
| `Telegram: Unauthorized` | Cek `TELEGRAM_BOT_TOKEN` dan pastikan sudah `/start` bot |
| `Threads: 401 Unauthorized` | Token Threads expired, generate ulang di Meta Developer |
| `Tavily: API key invalid` | Cek `TAVILY_API_KEY` di [tavily.com](https://tavily.com) |
| `Port already in use` | Hanya jalankan satu instance `main.py` |

---

## Lisensi

MIT License — bebas digunakan dan dimodifikasi.
