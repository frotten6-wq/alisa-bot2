import os
import asyncio
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, BufferedInputFile
)
from openai import OpenAI
from elevenlabs.client import ElevenLabs

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")
ELEVEN_API_KEY = "sk_0180bbc187eaee0d39c2649275619f8412183fbc6c472d59"
ADMIN_ID = 5044633928

client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
eleven = ElevenLabs(api_key=ELEVEN_API_KEY)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

users = {}
message_logs = []

def get_user(uid: int):
    if uid not in users:
        users[uid] = {
            "messages": 0,
            "voice_mode": False,
            "last_answer": "",
            "photo_prompt": ""
        }
    return users[uid]

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Профиль"), KeyboardButton(text="🛒 Магазин")],
        [KeyboardButton(text="🎤 Голосовой режим"), KeyboardButton(text="🖼 Фото")]
    ],
    resize_keyboard=True
)

def make_voice(text: str) -> bytes:
    audio = eleven.text_to_speech.convert(
        text=text[:400],
        voice_id="EXAVITQu4vr4xnSDxMaL",
        model_id="eleven_multilingual_v2"
    )
    return b"".join(audio)

def make_image(prompt: str) -> str:
    response = requests.post(
        "https://api.x.ai/v1/images/generations",
        headers={
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "grok-imagine-image-quality",
            "prompt": prompt,
            "n": 1
        },
        timeout=90
    )
    response.raise_for_status()
    return response.json()["data"][0]["url"]

# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет, я Алиса.", reply_markup=main_kb)

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        f"Админ-панель\n"
        f"Пользователей: {len(users)}\n"
        f"Записей в логе: {len(message_logs)}"
    )

@dp.message(Command("logs"))
async def cmd_logs(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    if not message_logs:
        await message.answer("Лог пуст")
        return
    text = "Последние сообщения:\n\n" + "\n".join(message_logs[-12:])
    await message.answer(text[:4000])

# ==================== КНОПКИ ====================
@dp.message(F.text == "📊 Профиль")
async def btn_profile(message: types.Message):
    user = get_user(message.from_user.id)
    free = "∞" if is_admin(message.from_user.id) else max(0, 30 - user["messages"])
    voice = "вкл" if user["voice_mode"] else "выкл"
    await message.answer(f"Бесплатных: {free}\nГолосовой режим: {voice}")

@dp.message(F.text == "🛒 Магазин")
async def btn_shop(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("Для тебя всё бесплатно")
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="20 сообщений — 15⭐", callback_data="buy_20")],
        [InlineKeyboardButton(text="50 сообщений — 35⭐", callback_data="buy_50")]
    ])
    await message.answer("Магазин:", reply_markup=keyboard)

@dp.message(F.text == "🎤 Голосовой режим")
async def btn_voice(message: types.Message):
    user = get_user(message.from_user.id)
    user["voice_mode"] = not user["voice_mode"]
    status = "включён" if user["voice_mode"] else "выключен"
    await message.answer(f"Голосовой режим {status}")

@dp.message(F.text == "🖼 Фото")
async def btn_photo(message: types.Message):
    await message.answer("Напиши описание фото, которое хочешь")

# ==================== ОСНОВНОЙ ЧАТ ====================
@dp.message(F.text)
async def handle_message(message: types.Message):
    text = message.text.strip()
    user_id = message.from_user.id
    user = get_user(user_id)
    admin = is_admin(user_id)

    message_logs.append(f"{user_id}: {text[:70]}")
    if len(message_logs) > 40:
        message_logs.pop(0)

    # Запрос фото
    lower = text.lower()
    if lower.startswith("фото") or lower.startswith("в ") or "бель" in lower:
        user["photo_prompt"] = text
        if admin:
            await message.answer("Генерирую фото...")
            try:
                url = make_image(f"beautiful young woman, {text}, photorealistic")
                await message.answer_photo(url)
            except Exception as e:
                await message.answer("Не получилось сгенерировать (возможно, модерация)")
                print(e)
        else:
            pay_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить 50⭐", callback_data="pay_photo")]
            ])
            await message.answer("Сгенерировать это фото за 50⭐?", reply_markup=pay_kb)
        return

    # Лимит сообщений
    if not admin and user["messages"] >= 30:
        await message.answer("Бесплатные сообщения закончились")
        return

    if not admin:
        user["messages"] += 1

    await bot.send_chat_action(message.chat.id, "typing")

    try:
        response = client.chat.completions.create(
            model="grok-4",
            messages=[
                {"role": "system", "content": "Ты Алиса, живая и естественная девушка. Поддерживай разговор."},
                {"role": "user", "content": text}
            ],
            temperature=0.85
        )
        answer = response.choices[0].message.content
        user["last_answer"] = answer

        if user["voice_mode"]:
            if admin:
                audio = make_voice(answer)
                await message.answer_voice(BufferedInputFile(audio, filename="voice.mp3"))
            else:
                voice_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Ответить голосовым — 10⭐", callback_data="pay_voice")]
                ])
                await message.answer(answer, reply_markup=voice_kb)
        else:
            await message.answer(answer)

    except Exception as e:
        await message.answer("Произошла ошибка, попробуй ещё раз")
        print(e)

# ==================== ОПЛАТА ====================
@dp.callback_query(F.data == "pay_photo")
async def pay_photo(callback: types.CallbackQuery):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Генерация фото",
        description="Фото от Алисы",
        payload="photo",
        currency="XTR",
        prices=[LabeledPrice(label="Фото", amount=50)]
    )
    await callback.answer()

@dp.callback_query(F.data == "pay_voice")
async def pay_voice(callback: types.CallbackQuery):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Голосовой ответ",
        description="Алиса ответит голосом",
        payload="voice",
        currency="XTR",
        prices=[LabeledPrice(label="Голос", amount=10)]
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def buy_messages(callback: types.CallbackQuery):
    amount = 20 if "20" in callback.data else 50
    price = 15 if amount == 20 else 35
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"{amount} сообщений",
        description="Пакет сообщений",
        payload=f"msg_{amount}",
        currency="XTR",
        prices=[LabeledPrice(label="Сообщения", amount=price)]
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload
    user = get_user(message.from_user.id)

    if payload == "photo":
        await message.answer("Генерирую фото...")
        try:
            url = make_image(user.get("photo_prompt") or "beautiful woman")
            await message.answer_photo(url)
        except Exception as e:
            await message.answer("Ошибка генерации фото")
            print(e)

    elif payload == "voice":
        await message.answer("Делаю голосовое...")
        try:
            audio = make_voice(user.get("last_answer") or "Привет")
            await message.answer_voice(BufferedInputFile(audio, filename="voice.mp3"))
        except Exception as e:
            await message.answer("Ошибка голосового")
            print(e)

    elif payload.startswith("msg_"):
        amount = int(payload.split("_")[1])
        user["messages"] = max(0, user["messages"] - amount)
        await message.answer(f"Добавлено {amount} сообщений")

# ==================== ЗАПУСК ====================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
