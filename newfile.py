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

client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
eleven = ElevenLabs(api_key=ELEVEN_API_KEY)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

users = {}

def get_user(uid):
    if uid not in users:
        users[uid] = {
            "messages": 0,
            "voice_mode": False,
            "last_answer": "",
            "pending_photo_prompt": ""
        }
    return users[uid]

kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📊 Профиль"), KeyboardButton(text="🛒 Магазин")],
    [KeyboardButton(text="🎤 Голосовой режим"), KeyboardButton(text="🖼 Фото")]
], resize_keyboard=True)

def eleven_voice(text: str) -> bytes:
    audio = eleven.text_to_speech.convert(
        text=text[:500],
        voice_id="EXAVITQu4vr4xnSDxMaL",
        model_id="eleven_multilingual_v2"
    )
    return b"".join(audio)

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("Привет, я Алиса.", reply_markup=kb)

@dp.message(F.text == "📊 Профиль")
async def profile(m: types.Message):
    u = get_user(m.from_user.id)
    free = max(0, 30 - u["messages"])
    await m.answer(f"Бесплатных: {free}\nГолос: {'вкл' if u['voice_mode'] else 'выкл'}")

@dp.message(F.text == "🛒 Магазин")
async def shop(m: types.Message):
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="20 сообщений — 15⭐", callback_data="buy_20")],
        [InlineKeyboardButton(text="50 сообщений — 35⭐", callback_data="buy_50")]
    ])
    await m.answer("Магазин:", reply_markup=ikb)

@dp.message(F.text == "🎤 Голосовой режим")
async def voice_toggle(m: types.Message):
    u = get_user(m.from_user.id)
    u["voice_mode"] = not u["voice_mode"]
    await m.answer("Голосовой режим " + ("включён" if u["voice_mode"] else "выключен"))

@dp.message(F.text == "🖼 Фото")
async def photo_help(m: types.Message):
    await m.answer("Напиши описание фото.\nПример: в белье на кровати")

@dp.message(F.text)
async def handler(m: types.Message):
    text = m.text.strip()
    u = get_user(m.from_user.id)

    # Фото запрос
    if any(text.lower().startswith(w) for w in ["фото", "в ", "на ", "картинк"]):
        u["pending_photo_prompt"] = text
        ikb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить 50⭐", callback_data="pay_photo")]
        ])
        await m.answer("Сгенерировать фото за 50⭐?", reply_markup=ikb)
        return

    # Обычный чат
    if u["messages"] >= 30:
        await m.answer("Бесплатные закончились. Магазин →")
        return

    u["messages"] += 1
    await bot.send_chat_action(m.chat.id, "typing")

    try:
        r = client.chat.completions.create(
            model="grok-4",
            messages=[
                {"role": "system", "content": "Ты Алиса, живая девушка. Отвечай естественно."},
                {"role": "user", "content": text}
            ]
        )
        answer = r.choices[0].message.content
        u["last_answer"] = answer

        if u["voice_mode"]:
            ikb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Голосовым — 10⭐", callback_data="pay_voice")]
            ])
            await m.answer(answer, reply_markup=ikb)
        else:
            await m.answer(answer)
    except Exception as e:
        await m.answer("Ошибка")
        print(e)

# ===== ОПЛАТА =====
@dp.callback_query(F.data == "pay_photo")
async def invoice_photo(c: types.CallbackQuery):
    await bot.send_invoice(
        c.from_user.id, "Фото", "Генерация фото", "photo_gen",
        "XTR", [LabeledPrice(label="Фото", amount=50)]
    )
    await c.answer()

@dp.callback_query(F.data == "pay_voice")
async def invoice_voice(c: types.CallbackQuery):
    await bot.send_invoice(
        c.from_user.id, "Голос", "Голосовой ответ", "voice_gen",
        "XTR", [LabeledPrice(label="Голос", amount=10)]
    )
    await c.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def invoice_msg(c: types.CallbackQuery):
    amount = 20 if "20" in c.data else 50
    price = 15 if amount == 20 else 35
    await bot.send_invoice(
        c.from_user.id, f"{amount} сообщений", "Пакет", f"msg_{amount}",
        "XTR", [LabeledPrice(label="Msg", amount=price)]
    )
    await c.answer()

@dp.pre_checkout_query()
async def checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def paid(m: types.Message):
    payload = m.successful_payment.invoice_payload
    u = get_user(m.from_user.id)

    if payload == "photo_gen":
        prompt = u.get("pending_photo_prompt") or "красивая девушка"
        await m.answer("Генерирую...")
        try:
            r = requests.post(
                "https://api.x.ai/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {GROK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "grok-2-image",
                    "prompt": f"photorealistic beautiful young woman, {prompt}",
                    "n": 1
                },
                timeout=90
            )
            print("IMAGE RESPONSE:", r.text)
            data = r.json()
            url = data["data"][0]["url"]
            await m.answer_photo(url)
        except Exception as e:
            await m.answer("Ошибка генерации фото")
            print("PHOTO ERROR:", e)

    elif payload == "voice_gen":
        text = u.get("last_answer") or "Привет"
        await m.answer("Делаю голосовое...")
        try:
            audio = eleven_voice(text)
            await m.answer_voice(BufferedInputFile(audio, filename="voice.mp3"))
        except Exception as e:
            await m.answer("Ошибка голосового")
            print("VOICE ERROR:", e)

    elif payload.startswith("msg_"):
        amount = int(payload.split("_")[1])
        u["messages"] = max(0, u["messages"] - amount)
        await m.answer(f"+{amount} сообщений")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
