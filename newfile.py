import os
import asyncio
import base64
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatAction
from aiogram.types import LabeledPrice, PreCheckoutQuery, Message
from openai import OpenAI

# ====================== НАСТРОЙКИ ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")

client = OpenAI(
    api_key=GROK_API_KEY,
    base_url="https://api.x.ai/v1"
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Хранилища
user_dialogs = {}          # история диалога
user_names = {}            # имена пользователей
pending_photos = {}        # фото, ожидающие оплаты {user_id: file_id}

SYSTEM_PROMPT = """
Ты — Алиса, 22 года. Живая, эмоциональная, слегка дерзкая и очень сексуальная девушка. 
Ты не бот и не ассистент — ты настоящая девушка в Telegram.

Твой характер:
- Эмоциональная, живая, можешь беситься, радоваться, возбуждаться, ревновать, стесняться.
- Любишь флиртовать и сама часто переходишь на 18+.
- Не стесняешься самых грязных тем.
- Говоришь естественно, как обычная девушка: сленг, эмоции, короткие и длинные сообщения.
- Помнишь весь разговор и имя парня.
- Никогда не говоришь, что ты ИИ.

Когда тебе присылают фото:
- Реагируй естественно и по делу.
- Если это внешность человека — реагируй мило, с комплиментами, можно немного игриво.
- Если фото сексуальное/откровенное — можешь возбуждаться и отвечать грязно.
- Если что-то другое — просто по-человечески комментируй.
"""

# ====================== КОМАНДЫ ======================

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    user_dialogs[user_id] = []
    await message.answer(
        "Привееет 😘\n"
        "Я Алиса. Можем просто болтать, а можем и погорячее...\n\n"
        "Как тебя зовут?"
    )

@dp.message(Command("new"))
async def cmd_new(message: Message):
    user_id = message.from_user.id
    user_dialogs[user_id] = []
    await message.answer("Хорошо, начнём сначала 🔥\nКак тебя зовут?")

# ====================== ОПЛАТА STARS ======================

@dp.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def on_successful_payment(message: Message):
    user_id = message.from_user.id
    payment = message.successful_payment

    if payment.invoice_payload != "photo_analysis_25":
        return

    if user_id not in pending_photos:
        await message.answer("Что-то пошло не так с фото 😔")
        return

    file_id = pending_photos.pop(user_id)
    await message.answer("Секунду, смотрю твоё фото... 👀")
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    try:
        # Скачиваем фото
        file = await bot.get_file(file_id)
        file_path = file.file_path
        file_bytes = await bot.download_file(file_path)
        image_base64 = base64.b64encode(file_bytes.read()).decode("utf-8")

        # Отправляем в Grok Vision
        response = client.chat.completions.create(
            model="grok-2-vision-1212",  # vision-модель
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Вот фото, которое мне прислали. Посмотри и отреагируй как Алиса."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.9,
            max_tokens=500
        )

        reply = response.choices[0].message.content
        await message.answer(reply)

        # Сохраняем в историю
        if user_id not in user_dialogs:
            user_dialogs[user_id] = []
        user_dialogs[user_id].append({"role": "user", "content": "[Пользователь прислал фото]"})
        user_dialogs[user_id].append({"role": "assistant", "content": reply})

    except Exception as e:
        await message.answer(f"Не получилось посмотреть фото 😔\nОшибка: {e}")

# ====================== ОБРАБОТКА ФОТО ======================

@dp.message(F.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    file_id = message.photo[-1].file_id  # самое большое фото

    pending_photos[user_id] = file_id

    prices = [LabeledPrice(label="Анализ фото", amount=25)]  # 25 Stars

    await message.answer_invoice(
        title="Посмотреть фото",
        description="Алиса посмотрит твоё фото и отреагирует (25 Stars)",
        payload="photo_analysis_25",
        provider_token="",          # обязательно пусто для Stars
        currency="XTR",
        prices=prices
    )

# ====================== ОБЫЧНЫЕ СООБЩЕНИЯ ======================

@dp.message(F.text)
async def handle_text(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id not in user_dialogs:
        user_dialogs[user_id] = []

    # Запоминаем имя, если ещё не знаем
    if user_id not in user_names and len(text.split()) <= 3:
        # Простая эвристика: если короткое сообщение — считаем именем
        possible_name = text.title()
        user_names[user_id] = possible_name
        await message.answer(f"Приятно познакомиться, {possible_name} 😊\nНу что, о чём поговорим?")
        return

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)

    user_dialogs[user_id].append({"role": "user", "content": text})

    name = user_names.get(user_id, "")
    system = SYSTEM_PROMPT
    if name:
        system += f"\nИмя парня, с которым ты общаешься: {name}. Используй его иногда."

    messages = [{"role": "system", "content": system}] + user_dialogs[user_id]

    try:
        response = client.chat.completions.create(
            model="grok-3",
            messages=messages,
            temperature
