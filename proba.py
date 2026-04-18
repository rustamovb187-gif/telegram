import logging
import asyncio
import sys
import os
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

try:
    import docx
except ImportError:
    print("pip install python-docx")
    sys.exit(1)

from config import API_TOKEN

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

user_data = {}

# 📄 PARSE
def parse_test_file(path, ext):
    if ext == "txt":
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        doc = docx.Document(path)
        content = "\n".join(p.text for p in doc.paragraphs)

    blocks = content.split("+++++")
    result = []

    for b in blocks:
        lines = [l.strip() for l in b.split("\n") if l.strip()]
        if len(lines) < 2:
            continue

        question = lines[0]
        options = []
        correct = None

        for line in lines[1:]:
            if set(line) == {"="}:
                continue
            if line.startswith("#"):
                text = line[1:].strip()
                options.append(text)
                correct = text
            else:
                options.append(line)

        if options:
            result.append({
                "text": question,
                "options": options,
                "correct": correct
            })

    return result


# 🚀 START
@dp.message(Command("start"))
async def start(msg: types.Message):
    await msg.answer("📄 Fayl yubor (.txt yoki .docx)")


# 📥 FILE
@dp.message(F.document)
async def handle_file(msg: types.Message):
    name = msg.document.file_name
    ext = name.split(".")[-1].lower()

    if ext not in ["txt", "docx"]:
        await msg.answer("❌ Faqat txt/docx")
        return

    status = await msg.answer("⏳ Yuklanmoqda...")

    os.makedirs("downloads", exist_ok=True)
    path = f"downloads/{name}"

    file = await bot.get_file(msg.document.file_id)
    await bot.download_file(file.file_path, path)

    questions = parse_test_file(path, ext)

    if not questions:
        await status.edit_text("❌ Savol topilmadi")
        return

    chunks = [questions[i:i+30] for i in range(0, len(questions), 30)]

    user_data[msg.from_user.id] = {"chunks": chunks}

    kb = InlineKeyboardBuilder()
    for i in range(len(chunks)):
        kb.button(text=f"{i+1}-qism ({len(chunks[i])})", callback_data=f"chunk_{i}")
    kb.adjust(4)

    await status.edit_text(
        f"✅ {len(questions)} ta savol\nQism tanlang:",
        reply_markup=kb.as_markup()
    )


# ▶️ BOSHLASH
@dp.callback_query(F.data.startswith("chunk_"))
async def start_quiz(call: types.CallbackQuery):
    user_id = call.from_user.id
    idx = int(call.data.split("_")[1])

    user_data[user_id].update({
        "chunk_index": idx,
        "index": 0,
        "score": 0
    })

    await call.message.answer(f"🚀 {idx+1}-qism boshlandi")
    await send_question(user_id)


# ❓ SAVOL
async def send_question(user_id):
    data = user_data[user_id]
    chunk = data["chunks"][data["chunk_index"]]
    q = chunk[data["index"]]

    options = [o[:100] for o in q["options"]]
    correct = q["correct"][:100] if q["correct"] else options[0]

    if correct not in options:
        options.insert(0, correct)

    options = options[:12]
    random.shuffle(options)

    correct_index = options.index(correct)
    data["correct_id"] = correct_index

    poll = await bot.send_poll(
        chat_id=user_id,
        question=q["text"][:300],
        options=options,
        type="quiz",
        correct_option_id=correct_index,
        is_anonymous=False
    )

    data["poll_id"] = poll.poll.id


# ✅ JAVOB
@dp.poll_answer()
async def handle_answer(ans: types.PollAnswer):
    user_id = ans.user.id
    data = user_data.get(user_id)

    if not data:
        return

    # ❗ faqat o‘z polli
    if ans.poll_id != data.get("poll_id"):
        return

    selected = ans.option_ids[0]

    if selected == data["correct_id"]:
        data["score"] += 1

    data["index"] += 1
    chunk = data["chunks"][data["chunk_index"]]

    # 🔚 BLOK TUGADI
    if data["index"] >= len(chunk):
        await bot.send_message(
            user_id,
            f"📊 Natija: {data['score']}/{len(chunk)}"
        )

        data["chunk_index"] += 1
        data["index"] = 0
        data["score"] = 0

        # 🔥 TAMOM
        if data["chunk_index"] >= len(data["chunks"]):
            await bot.send_message(user_id, "🏁 Test tugadi!")
            return

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➡️ Keyingi blok", callback_data="next")]
            ]
        )

        await bot.send_message(
            user_id,
            f"➡️ {data['chunk_index']+1}-qismni boshlash uchun bosing",
            reply_markup=kb
        )
        return

    await send_question(user_id)


# ▶️ KEYINGI BLOK
@dp.callback_query(F.data == "next")
async def next_block(call: types.CallbackQuery):
    user_id = call.from_user.id

    if user_id not in user_data:
        return

    await call.message.answer("🚀 Davom etamiz")
    await send_question(user_id)


# 🚀 RUN
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
