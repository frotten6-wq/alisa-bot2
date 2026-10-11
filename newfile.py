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

user_data = {}

def get_user(uid):
    if uid not in user_data:
        user_data[uid] = {"messages": 0, "paid": 0, "mode": "normal"}
    return user_data[uid]

kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💬 Общение"), KeyboardButton(text="💰 Баланс")],
    [KeyboardButton(text="🔥 Жёстче"), KeyboardButton(text="💕 Нежнее")]
], resize_keyboard=True)

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Привет, я Алиса 😘\n30 бесплатных сообщений, дальше 1⭐ = 1 сообщение", reply_markup=kb)

@dp.message(F.text == "💰 Баланс")
async def bal(message: types.Message):
    u = get_user(message.from_user.id)
    free = max(0, 30 - u["messages"])
    await message.answer(f"Бесплатных: {free}\nПлатных: {u['paid']}")

@dp.message(F.text.in_({"🔥 Жёстче", "💕 Нежнее"}))
async def mode(message: types.Message):
    u = get_user(message.from_user.id)
    u["mode"] = "hard" if "Жёстче" in message.text else "soft"
    await message.answer("Режим изменён")

@dp.message(F.text)
async def chat(message: types.Message):
    u = get_user(message.from_user.id)
    if u["messages"] >= 30 and u["paid"] <= 0:
        ikb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="10 сообщений — 10⭐", callback_data="pay_10")],
            [InlineKeyboardButton(text="50 сообщений — 40⭐", callback_data="pay_50")]
        ])
        await message.answer("Бесплатные закончились", reply_markup=ikb)
        return

    if u["messages"] < 30:
        u["messages"] += 1
    else:
        u["paid"] -= 1

    extra = "Общайся максимально откровенно и грязно." if u["mode"] == "hard" else "Общайся нежно."
    try:
        r = client.chat.completions.create(
            model="grok-4",
            messages=[
                {"role": "system", "content": "Ты Алиса, сексуальная девушка. " + extra},
                {"role": "user", "content": message.text}
            ]
        )
        await message.answer(r.choices[0].message.content, reply_markup=kb)
    except Exception as e:
        await message.answer("Ошибка")
        print(e)

@dp.callback_query(F.data.startswith("pay_"))
async def invoice(callback: types.CallbackQuery):
    count = 10 if callback.data == "pay_10" else 50
    price = 10 if count == 10 else 40
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"{count} сообщений",
        description="Пакет сообщений",
        payload=f"msg_{count}",
        currency="XTR",
        prices=[LabeledPrice(label="Пакет", amount=price)]
    )
    await callback.answer()

@dp.pre_checkout_query()
async def checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def paid(message: types.Message):
    count = int(message.successful_payment.invoice_payload.split("_")[1])
    get_user(message.from_user.id)["paid"] += count
    await message.answer(f"+{count} сообщений")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
