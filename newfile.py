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
            "relationship": 0,
            "name": None,
            "history": [],
            "voice_mode": False,
            "pending_photo": None
        }
    return users[uid]

kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Профиль"), KeyboardButton(text="🛒 Магазин")],
        [KeyboardButton(text="🎤 Голосовой режим"), KeyboardButton(text="🖼 Фото")]
    ],
    resize_keyboard=True
)

def make_voice(text: str) -> bytes:
    audio = eleven.text_to_speech.convert(
        text=text,
        voice_id="EXAVITQu4vr4xnSDxMaL",
        model_id="eleven_multilingual_v2"
    )
    return b"".join(audio)

# ==================== СТАРТ ====================
@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("Привет, я Алиса.", reply_markup=kb)

# ==================== КНОПКИ ====================
@dp.message(F.text == "📊 Профиль")
async def profile(m: types.Message):
    u = get_user(m.from_user.id)
    free = max(0, 30 - u["messages"])
    await m.answer(
        f"Бесплатных сообщений: {free}\n"
        f"Голосовой режим: {'вкл' if u['voice_mode'] else 'выкл'}"
    )

@dp.message(F.text == "🛒 Магазин")
async def shop(m: types.Message):
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="20 сообщений — 15⭐", callback_data="buy_msg_20")],
        [InlineKeyboardButton(text="50 сообщений — 35⭐", callback_data="buy_msg_50")],
        [InlineKeyboardButton(text="Голосовой ответ — 10⭐", callback_data="buy_voice")],
        [InlineKeyboardButton(text="Фото — 50⭐", callback_data="buy_photo")]
    ])
    await m.answer("Магазин:", reply_markup=ikb)

@dp.message(F.text == "🎤 Голосовой режим")
async def voice_mode(m: types.Message):
    u = get_user(m.from_user.id)
    u["voice_mode"] = not u["voice_mode"]
    status = "включён" if u["voice_mode"] else "выключен"
    await m.answer(f"Голосовой режим {status}\nОдин ответ = 10⭐")

@dp.message(F.text == "🖼 Фото")
async def photo_menu(m: types.Message):
    await m.answer("Напиши, какое фото хочешь.\nНапример: в белье на кровати\nЦена: 50⭐")

# ==================== ФОТО ====================
@dp.message(F.text.lower().startswith(("фото ", "в ", "на ")))
async def request_photo(m: types.Message):
    u = get_user(m.from_user.id)
    u["pending_photo"] = m.text
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить 50⭐", callback_data="pay_photo")]
    ])
    await m.answer("Сгенерировать это фото за 50⭐?", reply_markup=ikb)

# ==================== ЧАТ ====================
@dp.message(F.text)
async def chat(m: types.Message):
    u = get_user(m.from_user.id)

    if u["messages"] >= 30:
        ikb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Купить сообщения", callback_data="buy_msg_20")]
        ])
        await m.answer("Бесплатные сообщения закончились", reply_markup=ikb)
        return

    u["messages"] += 1
    await bot.send_chat_action(m.chat.id, "typing")

    try:
        r = client.chat.completions.create(
            model="grok-4",
            messages=[
                {"role": "system", "content": "Ты Алиса, живая девушка 23 лет. Общайся естественно и поддерживай разговор."},
                {"role": "user", "content": m.text}
            ],
            temperature=0.85
        )
        answer = r.choices[0].message.content

        if u["voice_mode"]:
            ikb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Ответить голосовым — 10⭐", callback_data="pay_voice")]
            ])
            await m.answer(answer, reply_markup=ikb)
        else:
            await m.answer(answer)
    except Exception as e:
        await m.answer("Ошибка, попробуй ещё раз")
        print(e)

# ==================== ОПЛАТА ====================
@dp.callback_query(F.data == "pay_photo")
async def pay_photo(c: types.CallbackQuery):
    await bot.send_invoice(
        chat_id=c.from_user.id,
        title="Генерация фото",
        description="Фото от Алисы",
        payload="photo",
        currency="XTR",
        prices=[LabeledPrice(label="Фото", amount=50)]
    )
    await c.answer()

@dp.callback_query(F.data == "pay_voice")
async def pay_voice(c: types.CallbackQuery):
    await bot.send_invoice(
        chat_id=c.from_user.id,
        title="Голосовой ответ",
        description="Алиса ответит голосовым",
        payload="voice",
        currency="XTR",
        prices=[LabeledPrice(label="Голос", amount=10)]
    )
    await c.answer()

@dp.callback_query(F.data.startswith("buy_msg_"))
async def buy_messages(c: types.CallbackQuery):
    amount = 20 if "20" in c.data else 50
    price = 15 if amount == 20 else 35
    await bot.send_invoice(
        chat_id=c.from_user.id,
        title=f"{amount} сообщений",
        description="Пакет сообщений",
        payload=f"messages_{amount}",
        currency="XTR",
        prices=[LabeledPrice(label="Сообщения", amount=price)]
    )
    await c.answer()

@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def success(m: types.Message):
    payload = m.successful_payment.invoice_payload
    u = get_user(m.from_user.id)

    if payload == "photo":
        prompt = u.get("pending_photo") or "красивая девушка"
        await m.answer("Генерирую фото...")
        try:
            resp = requests.post(
                "https://api.x.ai/v1/images/generations",
                headers={"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"},
                json={"model": "grok-imagine-image-quality", "prompt": f"красивая молодая девушка, {prompt}, высокое качество, реалистично", "n": 1},
                timeout=60
            )
            url = resp.json()["data"][0]["url"]
            await m.answer_photo(url)
        except Exception as e:
            await m.answer("Не получилось сгенерировать фото")
            print(e)

    elif payload == "voice":
        await m.answer("Делаю голосовое...")
        # Здесь нужно сохранить последний ответ. Упрощённо:
        await m.answer("Голосовое будет в следующем сообщении (доработаем)")

    elif payload.startswith("messages_"):
        amount = int(payload.split("_")[1])
        u["messages"] = max(0, u["messages"] - amount)
        await m.answer(f"Добавлено {amount} сообщений")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
