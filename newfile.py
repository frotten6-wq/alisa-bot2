import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")

client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

users = {}

def get_user(uid):
    if uid not in users:
        users[uid] = {
            "messages": 0,
            "paid": 0,
            "relationship": 0,  # 0-100
            "mood": "normal",
            "name": None
        }
    return users[uid]

def get_relationship_level(points):
    if points < 20:
        return "Незнакомка"
    elif points < 50:
        return "Знакомая"
    elif points < 80:
        return "Близкая"
    else:
        return "Твоя"

main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💬 Написать"), KeyboardButton(text="📊 Профиль")],
    [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="🎁 Подарок")],
    [KeyboardButton(text="🎤 Голосовое (10⭐)")]
], resize_keyboard=True)

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет. Я Алиса.\n\n"
        "30 бесплатных сообщений, дальше платно.\n"
        "Чем больше общаемся — тем я открытее.",
        reply_markup=main_kb
    )

@dp.message(F.text == "📊 Профиль")
async def profile(message: types.Message):
    u = get_user(message.from_user.id)
    free = max(0, 30 - u["messages"])
    level = get_relationship_level(u["relationship"])
    await message.answer(
        f"Уровень отношений: {level} ({u['relationship']}/100)\n"
        f"Бесплатных сообщений: {free}\n"
        f"Платных: {u['paid']}\n"
        f"Настроение: {u['mood']}"
    )

@dp.message(F.text == "🛒 Магазин")
async def shop(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="20 сообщений — 15⭐", callback_data="pay_20")],
        [InlineKeyboardButton(text="50 сообщений — 35⭐", callback_data="pay_50")],
        [InlineKeyboardButton(text="Подписка на день — 80⭐", callback_data="pay_sub")]
    ])
    await message.answer("Магазин:", reply_markup=kb)

@dp.message(F.text == "🎁 Подарок")
async def gift_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Цветы — 15⭐", callback_data="gift_flowers")],
        [InlineKeyboardButton(text="Ужин — 40⭐", callback_data="gift_dinner")],
        [InlineKeyboardButton(text="Бельё — 60⭐", callback_data="gift_lingerie")]
    ])
    await message.answer("Что хочешь подарить?", reply_markup=kb)

@dp.message(F.text)
async def chat(message: types.Message):
    if message.text in ["🎤 Голосовое (10⭐)"]:
        await message.answer("Голосовые пока в разработке")
        return

    u = get_user(message.from_user.id)

    if u["messages"] >= 30 and u["paid"] <= 0:
        await message.answer("Бесплатные закончились. Загляни в 🛒 Магазин")
        return

    if u["messages"] < 30:
        u["messages"] += 1
    else:
        u["paid"] -= 1

    # Рост отношений
    u["relationship"] = min(100, u["relationship"] + 1)

    level = get_relationship_level(u["relationship"])
    openness = "очень сдержанно" if u["relationship"] < 30 else "открыто и откровенно" if u["relationship"] > 70 else "с флиртом"

    await bot.send_chat_action(message.chat.id, "typing")

    try:
        r = client.chat.completions.create(
            model="grok-4",
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Ты Алиса. Уровень отношений с пользователем: {level}. "
                        f"Общайся {openness}. "
                        "Используй эмодзи редко и только когда это уместно. "
                        "Будь живой, естественной, как в реальной переписке."
                    )
                },
                {"role": "user", "content": message.text}
            ],
            temperature=0.8,
            max_tokens=350
        )
        await message.answer(r.choices[0].message.content)
    except Exception as e:
        await message.answer("Что-то сломалось, напиши ещё раз")
        print(e)

# Оплата
@dp.callback_query(F.data.startswith("pay_"))
async def pay(callback: types.CallbackQuery):
    data = callback.data
    if data == "pay_20":
        title, price, amount = "20 сообщений", 15, 20
    elif data == "pay_50":
        title, price, amount = "50 сообщений", 35, 50
    else:
        title, price, amount = "Подписка на день", 80, 200

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=title,
        description="Покупка в боте Алисы",
        payload=f"buy_{amount}",
        currency="XTR",
        prices=[LabeledPrice(label=title, amount=price)]
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("gift_"))
async def gift(callback: types.CallbackQuery):
    gifts = {
        "gift_flowers": (15, 5, "цветы"),
        "gift_dinner": (40, 12, "ужин"),
        "gift_lingerie": (60, 20, "бельё")
    }
    price, rel, name = gifts[callback.data]
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Подарок: {name}",
        description="Подарок для Алисы",
        payload=f"gift_{rel}",
        currency="XTR",
        prices=[LabeledPrice(label=name, amount=price)]
    )
    await callback.answer()

@dp.pre_checkout_query()
async def checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def success(message: types.Message):
    payload = message.successful_payment.invoice_payload
    u = get_user(message.from_user.id)
    if payload.startswith("buy_"):
        amount = int(payload.split("_")[1])
        u["paid"] += amount
        await message.answer(f"Добавлено {amount} сообщений")
    elif payload.startswith("gift_"):
        rel = int(payload.split("_")[1])
        u["relationship"] = min(100, u["relationship"] + rel)
        await message.answer("Спасибо за подарок... мне приятно")

async def main():
