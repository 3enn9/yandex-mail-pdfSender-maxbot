import asyncio
import io
import os
import ssl
import time
import pdfplumber
from io import BytesIO
import re
import fitz
from telegram import Bot
from dotenv import load_dotenv

import certifi
from imapclient import IMAPClient
import pyzmail

HOST = 'imap.yandex.ru'

ssl_context = ssl.create_default_context(cafile=certifi.where())

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")


def process_message(server, uid):
    raw_message = server.fetch([uid], ['BODY.PEEK[]', 'FLAGS'])
    message = pyzmail.PyzMessage.factory(raw_message[uid][b'BODY[]'])

    from_ = message.get_addresses('from')

    if from_[0][1] != "ratavina@mail.ru":
        return

    for part in message.mailparts:
        if part.filename and part.filename.endswith(".pdf") and "сч " in part.filename:

            pdf_bytes = part.get_payload()

            pdf_file = BytesIO(pdf_bytes)

            with pdfplumber.open(pdf_file) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""

            check = parse_invoice(text)
            result = os.path.splitext(part.filename)[0].strip('"') + "\n" + check

            loop = asyncio.new_event_loop()
            loop.run_until_complete(send_pdf_as_images(pdf_bytes, result))

            print(uid, result)


def idle_loop():
    last_uid = 56886

    while True:
        try:
            with IMAPClient(HOST, ssl=True) as server:
                server.login(USERNAME, PASSWORD)
                server.select_folder('INBOX')

                print("✅ подключено")

                while True:
                    server.idle()

                    responses = server.idle_check(timeout=60)
                    server.idle_done()

                    messages = server.search(['UID', f'{last_uid + 1}:*'])

                    if messages:
                        for uid in messages:
                            if uid > last_uid:
                                process_message(server, uid)

                        last_uid = max(messages)

        except Exception as e:
            print("⚠️ ошибка:", e)
            print("🔄 переподключение...")
            time.sleep(5)


def parse_invoice(text: str):
    buyer = re.search(
        r"Покупатель\s+(.*?)(?=\s*,?\s*ИНН)",
        text,
        re.S
    )

    if buyer:
        buyer = re.sub(r'\s+', ' ', buyer.group(1)).strip()

    if buyer is None:
        return ""
    return buyer


async def send_pdf_as_images(pdf_bytes, text):
    bot = Bot(token=BOT_TOKEN)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for i, page in enumerate(doc):
        pix = page.get_pixmap()
        img_bytes = pix.tobytes("png")

        bio = io.BytesIO(img_bytes)
        bio.name = f"page_{i}.png"
        bio.seek(0)

        await bot.send_photo(
            chat_id=CHAT_ID,
            photo=bio,
            caption=text
        )

if __name__ == "__main__":
    idle_loop()