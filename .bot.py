import os
import asyncio
from pathlib import Path

from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import uvicorn

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from mutagen import File as MutagenFile


# =========================
# تنظیمات
# =========================

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])

ARTIST = "@playtrix13"

COVER_PATH = Path("cover.jpg")

PORT = int(os.environ.get("PORT", "10000"))

HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

if HOSTNAME:
    WEBHOOK_URL = f"https://{HOSTNAME}/telegram"
else:
    WEBHOOK_URL = None


# =========================
# پوشه فایل‌های موقت
# =========================

PENDING_DIR = Path("/tmp/pending")
PENDING_DIR.mkdir(parents=True, exist_ok=True)

pending_titles = {}


# =========================
# بررسی کاربر
# =========================

def is_allowed(update: Update) -> bool:
    user = update.effective_user

    return (
        user is not None
        and user.id == ALLOWED_USER_ID
    )


# =========================
# پیدا کردن اسم آهنگ
# =========================

def get_title(path: Path) -> str | None:

    try:

        audio = MutagenFile(
            path,
            easy=True
        )

        if audio:

            title = audio.get("title")

            if title and title[0].strip():

                return title[0].strip()

    except Exception:

        pass

    # استفاده از اسم فایل
    filename = path.stem.strip()

    if filename and filename.lower() not in [
        "music",
        "audio",
        "unknown",
        "input",
    ]:

        return filename

    return None


# =========================
# اجرای FFmpeg
# =========================

async def run_ffmpeg(*args):

    process = await asyncio.create_subprocess_exec(

        "ffmpeg",

        *args,

        stdout=asyncio.subprocess.PIPE,

        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:

        raise RuntimeError(
            stderr.decode(
                errors="ignore"
            )[-2500:]
        )


# =========================
# پردازش آهنگ
# =========================

async def process_music(
    message,
    input_file: Path,
    title: str,
):

    output_file = input_file.with_name(
        "output.mp3"
    )

    voice_file = input_file.with_name(
        "voice.ogg"
    )

    try:

        # -------------------------
        # ساخت MP3 با کاور
        # -------------------------

        if COVER_PATH.exists():

            await run_ffmpeg(

                "-y",

                "-i",
                str(input_file),

                "-i",
                str(COVER_PATH),

                "-map",
                "0:a",

                "-map",
                "1:v",

                "-c:a",
                "copy",

                "-c:v",
                "mjpeg",

                "-id3v2_version",
                "3",

                "-metadata",
                f"title={title}",

                "-metadata",
                f"artist={ARTIST}",

                "-metadata:s:v",
                "title=Album cover",

                "-metadata:s:v",
                "comment=Cover (front)",

                str(output_file),
            )

        else:

            # اگر cover.jpg هنوز وجود نداشت
            await run_ffmpeg(

                "-y",

                "-i",
                str(input_file),

                "-c:a",
                "copy",

                "-id3v2_version",
                "3",

                "-metadata",
                f"title={title}",

                "-metadata",
                f"artist={ARTIST}",

                str(output_file),
            )

        # -------------------------
        # ساخت ویس ۶۰ ثانیه‌ای
        # -------------------------

        await run_ffmpeg(

            "-y",

            "-i",
            str(input_file),

            "-t",
            "60",

            "-vn",

            "-c:a",
            "libopus",

            "-b:a",
            "96k",

            str(voice_file),
        )

        # -------------------------
        # ارسال آهنگ
        # -------------------------

        with open(
            output_file,
            "rb"
        ) as music:

            await message.reply_audio(

                audio=music,

                title=title,

                performer=ARTIST,

                caption=(
                    f"🎵 {title}\n"
                    f"👤 {ARTIST}"
                ),
            )

        # -------------------------
        # ارسال ویس
        # -------------------------

        with open(
            voice_file,
            "rb"
        ) as voice:

            await message.reply_voice(

                voice=voice,

                caption="🎙️ یک دقیقه اول آهنگ",
            )

    except Exception as error:

        await message.reply_text(

            "❌ هنگام پردازش آهنگ خطایی رخ داد.\n\n"
            f"{str(error)[:700]}"
        )

    finally:

        try:
            input_file.unlink(missing_ok=True)
        except:
            pass

        try:
            output_file.unlink(missing_ok=True)
        except:
            pass

        try:
            voice_file.unlink(missing_ok=True)
        except:
            pass


# =========================
# دریافت آهنگ
# =========================

async def process_received_music(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_allowed(update):
        return

    message = update.message

    if not message:
        return

    telegram_file = None

    filename = "music.mp3"

    if message.audio:

        telegram_file = (
            await message.audio.get_file()
        )

        filename = (
            message.audio.file_name
            or "music.mp3"
        )

    elif message.document:

        mime = (
            message.document.mime_type
            or ""
        )

        if not mime.startswith("audio/"):
            return

        telegram_file = (
            await message.document.get_file()
        )

        filename = (
            message.document.file_name
            or "music.mp3"
        )

    else:
        return

    if not filename.lower().endswith(".mp3"):

        await message.reply_text(
            "❌ فعلاً فقط فایل MP3 رو بفرست."
        )

        return

    await message.chat.send_action(
        ChatAction.TYPING
    )

    input_file = (
        PENDING_DIR
        / f"{ALLOWED_USER_ID}_input.mp3"
    )

    await telegram_file.download_to_drive(
        input_file
    )

    title = get_title(input_file)

    # اگر اسم آهنگ پیدا نشد
    if not title:

        pending_titles[
            ALLOWED_USER_ID
        ] = input_file

        await message.reply_text(

            "🎵 اسم آهنگ پیدا نشد.\n\n"
            "اسم آهنگ رو برام بفرست تا با همون اسم "
            "پردازشش کنم."
        )

        return

    await process_music(

        message,

        input_file,

        title,
    )


# =========================
# دریافت اسم دستی
# =========================

async def manual_title(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_allowed(update):
        return

    message = update.message

    if not message or not message.text:
        return

    user_id = update.effective_user.id

    input_file = pending_titles.get(
        user_id
    )

    if not input_file:
        return

    title = message.text.strip()

    if not title:
        return

    pending_titles.pop(
        user_id,
        None
    )

    await message.chat.send_action(
        ChatAction.TYPING
    )

    await process_music(

        message,

        input_file,

        title,
    )


# =========================
# Start
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_allowed(update):
        return

    await update.message.reply_text(

        "🎵 آماده‌ام!\n\n"
        "فایل MP3 رو بفرست."
    )


# =========================
# ساخت Telegram Application
# =========================

application = (
    Application
    .builder()
    .token(BOT_TOKEN)
    .build()
)


application.add_handler(
    CommandHandler(
        "start",
        start
    )
)


application.add_handler(
    MessageHandler(
        filters.AUDIO
        | filters.Document.AUDIO,
        process_received_music
    )
)


application.add_handler(
    MessageHandler(
        filters.TEXT
        & ~filters.COMMAND,
        manual_title
    )
)


# =========================
# FastAPI
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):

    await application.initialize()

    await application.start()

    if WEBHOOK_URL:

        await application.bot.set_webhook(
            url=WEBHOOK_URL
        )

    yield

    if WEBHOOK_URL:

        await application.bot.delete_webhook()

    await application.stop()

    await application.shutdown()


app = FastAPI(
    lifespan=lifespan
)


@app.get("/")
async def home():

    return {
        "status": "online",
        "bot": "playtrix music bot"
    }


@app.post("/telegram")
async def telegram_webhook(
    request: Request
):

    data = await request.json()

    update = Update.de_json(
        data,
        application.bot
    )

    await application.update_queue.put(
        update
    )

    return {
        "ok": True
    }


# =========================
# اجرای سرور
# =========================

if __name__ == "__main__":

    uvicorn.run(

        app,

        host="0.0.0.0",

        port=PORT
    )
