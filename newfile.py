import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from openai import OpenAI

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROK_API_KEY = os.getenv("GROK_API_KEY")

client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

users = {}

def get_user(uid):
    if uid not in users:
        users[uid] = {"messages": 0, "paid": 0, "relationship": 0}
    return users[uid]

def get_level(p):
    if p < 25: return "знакомство"
    if p < 60: return "флирт"
    return "близкие"

kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📊 Профиль"), KeyboardButton(text="🛒 Магазин")],
    [KeyboardButton(text="🎁 Подарок")]
], resize_keyboard=True)

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("Привет, я Алиса.\n30 бесплатных сообщений.", reply_markup=kb)

@dp.message(F.text == "📊 Профиль")
async def profile(m: types.Message):
    u = get_user(m.from_user.id)
    free = max(0, 30 - u["messages"])
    await m.answer(f"Уровень: {get_level(u['relationship'])}\nБесплатных: {free}\nПлатных: {u['paid']}")

@dp.message(F.text == "🛒 Магазин")
async def shop(m: types.Message):
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="20 сообщений — 15⭐", callback_data="pay_20")],
        [InlineKeyboardButton(text="50 сообщений — 35⭐", callback_data="pay_50")]
    ])
    await m.answer("Магазин:", reply_markup=ikb)

@dp.message(F.text == "🎁 Подарок")
async def gift_menu(m: types.Message):
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Цветы — 15⭐", callback_data="gift_5")],
        [InlineKeyboardButton(text="Бельё — 60⭐", callback_data="gift_20")]
    ])
    await m.answer("Подарок:", reply_markup=ikb)

@dp.message(F.text)
async def chat(m: types.Message):
    u = get_user(m.from_user.id)
    if u["messages"] >= 30 and u["paid"] <= 0:
        await m.answer("Бесплатные закончились. Магазин 🛒")
        return
    if u["messages"] < 30:
        u["messages"] += 1
    else:
        u["paid"] -= 1
    u["relationship"] = min(100, u["relationship"] + 1)

    await bot.send_chat_action(m.chat.id, "typing")
    await asyncio.sleep(1)

    system = (
        "Ты Алиса, 23 года. Живая и естественная. "
        "Поддерживаешь разговор. Если пишут обычно — лёгкий флирт. "
        "Если откровенно — подстраиваешься и становишься открытее. "
        "Не отказывай резко. Эмодзи почти не используй. "
        f"Стадия: {get_level(u['relationship'])}."
    )
    try:
        r = client.chat.completions.create(
            model="grok-4",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": m.text}],
            temperature=0.8
        )
        await m.answer(r.choices[0].message.content)
    except:
        await m.answer("Секунду...")

@dp.callback_query(F.data.startswith("pay_"))
async def pay(c: types.CallbackQuery):
    amount = 20 if c.data == "pay_20" else 50
    price = 15 if amount == 20 else 35
    await bot.send_invoice(c.from_user.id, f"{amount} сообщений", "Пакет", f"buy_{amount}", "XTR", [LabeledPrice(label="x", amount=price)])
    await c.answer()

@dp.callback_query(F.data.startswith("gift_"))
async def gift(c: types.CallbackQuery):
    rel = 5 if "5" in c.data else 20
    price = 15 if rel == 5 else 60
    await bot.send_invoice(c.from_user.id, "Подарок", "Для Алисы", f"gift_{rel}", "XTR", [LabeledPrice(label="x", amount=price)])
    await c.answer()

@dp.pre_checkout_query()
async def pre(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def ok(m: types.Message):
    p = m.successful_payment.invoice_payload
    u = get_user(m.from_user.id)
    if p.startswith("buy_"):
