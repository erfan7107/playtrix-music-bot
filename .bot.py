import os
import asyncio
import tempfile
from pathlib import Path

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


BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["ALLOWED_USER_ID"])

ARTIST = "@playtrix13"
COVER_PATH = Path("cover.jpg")


def is_allowed(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == ALLOWED_USER_ID


def get_title(path: Path) -> str:
    try:
        audio = MutagenFile(path, easy=True)

        if audio:
            title = audio.get("title")

            if title and title[0].strip():
                return title[0].strip()

    except Exception:
        pass

    return path.stem.strip() or "Unknown"


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
            stderr.decode(errors="ignore")[-2500:]
        )


async def process_music(
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

        telegram_file = await message.audio.get_file()

        filename = (
            message.audio.file_name
            or "music.mp3"
        )

    elif message.document:

        mime = message.document.mime_type or ""

        if not mime.startswith("audio/"):
            return

        telegram_file = await message.document.get_file()

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

    with tempfile.TemporaryDirectory() as temp_dir:

        temp = Path(temp_dir)

        input_file = temp / "input.mp3"
        output_file = temp / "output.mp3"
        voice_file =
