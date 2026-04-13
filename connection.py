import asyncio
import io
import json
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
    raw_message = server.fetch([uid], ['BODY[]', 'FLAGS'])
    message = pyzmail.PyzMessage.factory(raw_message[uid][b'BODY[]'])

    subject = message.get_subject()
    from_ = message.get_addresses('from')

    if from_[0][1] != "ratavina@mail.ru":
        return

    if message.text_part:
        body = message.text_part.get_payload().decode(message.text_part.charset)
    elif message.html_part:
        body = message.html_part.get_payload().decode(message.html_part.charset)
    else:
        body = ""

    for part in message.mailparts:
        if part.filename and part.filename.endswith(".pdf") and "сч " in part.filename:

            pdf_bytes = part.get_payload()

            pdf_file = BytesIO(pdf_bytes)

            with pdfplumber.open(pdf_file) as pdf:
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""

            # result = parse_invoice(text)
            result = os.path.splitext(part.filename)[0].strip('"')

            loop = asyncio.new_event_loop()
            loop.run_until_complete(send_pdf_as_images(pdf_bytes, result))

            print(uid, result)

    # print("📩 Новое письмо!")
    # print("UID: ", uid)
    # print("От:", from_)
    # print("Тема:", subject)
    # print("Текст:", body[:200])
    # print("-" * 40)


def idle_loop():
    last_uid = 56747

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
    result = {}

    buyer = re.search(r"Покупатель\s+(.*?)(?=Основание|№|Товары|$)", text, re.S)
    if buyer:
        result["buyer"] = extract_org_name(buyer.group(1))

    return result


async def send_pdf_as_images(pdf_bytes, text):
    bot = Bot(token=BOT_TOKEN)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    # text = json.dumps(text, ensure_ascii=False, indent=2)

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


def extract_org_name(text):
    # берём только ООО/ИП/АО и т.п.
    match = re.search(
        r'(ООО|ИП|АО|ЗАО|ПАО|Общество\s+с\s+ограниченной\s+ответственностью|Индивидуальный\s+предприниматель)\s*"?([^,\n]+)"?',
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    name = match.group(0)

    # убираем хвосты (ИНН, КПП, адреса)
    name = re.sub(r'ИНН.*', '', name)
    name = re.sub(r'КПП.*', '', name)
    name = re.sub(r',.*', '', name)

    return name.strip()

if __name__ == "__main__":
    idle_loop()
