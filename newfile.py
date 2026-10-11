import os
import asyncio
import requests
from datetime import datetime, timedelta
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

SCENARIOS = {
    "evening": "Тихий вечер дома. Ты расслаблена и общаешься тепло.",
    "date": "Вы на свидании. Ты игривая и заинтересованная.",
    "support": "Человеку тяжело. Ты внимательная и поддерживающая.",
    "spicy": "Откровенная атмосфера. Ты раскрепощена."
}

def get_user(uid: int):
    if uid not in users:
        users[uid] = {
            "messages": 0,
            "paid": 0,
            "relationship": 5,
            "scenario": None,
            "voice_mode": False,
            "name": None,
            "history": [],
            "last_answer": "",
            "subscription_until": None,
            "bonus_claimed": None
        }
    return users[uid]

def is_admin(uid):
    return uid == ADMIN_ID

def has_sub(u):
    if not u.get("subscription_until"):
        return False
    return datetime.fromisoformat(u["subscription_until"]) > datetime.now()

def rel_text(p):
    if p < 25: return "знакомство"
    if p < 55: return "симпатия"
    return "близкие"

main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💬 Чат"), KeyboardButton(text="📊 Профиль")],
    [KeyboardButton(text="🎭 Сценарии"), KeyboardButton(text="🛒 Магазин")],
    [KeyboardButton(text="🎁 Бонус"), KeyboardButton(text="🖼 Фото")],
    [KeyboardButton(text="🎤 Голос")]
], resize_keyboard=True)

def gen_voice(text: str) -> bytes:
    audio = eleven.text_to_speech.convert(
        text=text[:400],
        voice_id="EXAVITQu4vr4xnSDxMaL",
        model_id="eleven_multilingual_v2"
    )
    return b"".join(audio)

# ===== КОМАНДЫ =====
@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer(
        "Привет. Я Алиса.\n"
        "Можем поболтать или выбрать сценарий.",
        reply_markup=main_kb
    )

@dp.message(Command("users"))
async def cmd_users(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    if not users:
        await m.answer("Нет пользователей")
        return
    text = "Пользователи:\n\n"
    for uid, u in list(users.items())[:25]:
        text += f"{uid} | сообщ: {u['messages']} | отн: {u['relationship']}\n"
    text += "\n/user ID — подробнее"
    await m.answer(text)

@dp.message(Command("user"))
async def cmd_user(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) < 2:
        await m.answer("/user 123456")
        return
    try:
        uid = int(parts[1])
    except:
        await m.answer("Неверный ID")
        return
    if uid not in users:
        await m.answer("Не найден")
        return
    u = users[uid]
    await m.answer(
        f"ID: {uid}\n"
        f"Имя: {u.get('name') or '—'}\n"
        f"Сообщений: {u['messages']}\n"
        f"Платных: {u['paid']}\n"
        f"Отношения: {u['relationship']} ({rel_text(u['relationship'])})\n"
        f"Сценарий: {u.get('scenario') or 'нет'}\n"
        f"Подписка: {'да' if has_sub(u) else 'нет'}\n\n"
        f"/history {uid}"
    )

@dp.message(Command("history"))
async def cmd_history(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    parts = m.text.split()
    if len(parts) < 2:
        await m.answer("/history 123456")
        return
    try:
        uid = int(parts[1])
    except:
        return
    if uid not in users or not users[uid]["history"]:
        await m.answer("Истории нет")
        return
    text = f"История {uid}:\n\n"
    for msg in users[uid]["history"][-12:]:
        who = "User" if msg["role"] == "user" else "Alisa"
        text += f"{who}: {msg['content'][:120]}\n\n"
    await m.answer(text[:4000])

# ===== КНОПКИ =====
@dp.message(F.text == "📊 Профиль")
async def profile(m: types.Message):
    u = get_user(m.from_user.id)
    free = "∞" if is_admin(m.from_user.id) or has_sub(u) else max(0, 30 - u["messages"])
    await m.answer(
        f"Отношения: {rel_text(u['relationship'])} ({u['relationship']})\n"
        f"Сценарий: {u['scenario'] or 'нет'}\n"
        f"Бесплатных: {free}\n"
        f"Платных: {u['paid']}"
    )

@dp.message(F.text == "🎭 Сценарии")
async def scenarios(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Вечер дома", callback_data="sc_evening")],
        [InlineKeyboardButton(text="Свидание", callback_data="sc_date")],
        [InlineKeyboardButton(text="Поддержка", callback_data="sc_support")],
        [InlineKeyboardButton(text="Откровенно", callback_data="sc_spicy")],
        [InlineKeyboardButton(text="Убрать", callback_data="sc_none")]
    ])
    await m.answer("Сценарий:", reply_markup=kb)

@dp.message(F.text == "🛒 Магазин")
async def shop(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="40 сообщений — 25⭐", callback_data="buy_40")],
        [InlineKeyboardButton(text="День — 70⭐", callback_data="sub_day")],
        [InlineKeyboardButton(text="Неделя — 250⭐", callback_data="sub_week")]
    ])
    await m.answer("Магазин:", reply_markup=kb)

@dp.message(F.text == "🎁 Бонус")
async def bonus(m: types.Message):
    u = get_user(m.from_user.id)
    now = datetime.now()
    if u["bonus_claimed"]:
        if now - datetime.fromisoformat(u["bonus_claimed"]) < timedelta(hours=20):
            await m.answer("Уже получал")
            return
    u["paid"] += 8
    u["bonus_claimed"] = now.isoformat()
    await m.answer("+8 сообщений")

@dp.message(F.text == "🎤 Голос")
async def voice_btn(m: types.Message):
    u = get_user(m.from_user.id)
    u["voice_mode"] = not u["voice_mode"]
    await m.answer("Голос " + ("вкл" if u["voice_mode"] else "выкл"))

@dp.message(F.text == "🖼 Фото")
async def photo_btn(m: types.Message):
    await m.answer("Напиши описание фото")

@dp.callback_query(F.data.startswith("sc_"))
async def set_sc(c: types.CallbackQuery):
    key = c.data.split("_", 1)[1]
    u = get_user(c.from_user.id)
    u["scenario"] = None if key == "none" else key
    await c.message.answer("Готово")
    await c.answer()

@dp.message(F.text)
async def chat(m: types.Message):
    text = m.text.strip()
    uid = m.from_user.id
    u = get_user(uid)
    admin = is_admin(uid)

    if not admin and not has_sub(u) and u["messages"] >= 30 and u["paid"] <= 0:
        await m.answer("Лимит")
        return

    if not admin and not has_sub(u):
        if u["messages"] < 30:
            u["messages"] += 1
        else:
            u["paid"] -= 1

    u["relationship"] = min(100, u["relationship"] + 1)
    u["history"].append({"role": "user", "content": text})
    if len(u["history"]) > 15:
        u["history"] = u["history"][-15:]

    await bot.send_chat_action(m.chat.id, "typing")

    sc = SCENARIOS.get(u["scenario"], "")
    system = (
        "Ты Алиса, 23 года. Живая и естественная. "
        "Отвечай разнообразно и по ситуации. "
        f"{sc} Уровень: {rel_text(u['relationship'])}."
    )

    try:
        r = client.chat.completions.create(
            model="grok-4",
            messages=[{"role": "system", "content": system}] + u["history"],
            temperature=0.88
        )
        ans = r.choices[0].message.content
        u["last_answer"] = ans
        u["history"].append({"role": "assistant", "content": ans})

        if u["voice_mode"] and admin:
            await m.answer_voice(BufferedInputFile(gen_voice(ans), "v.mp3"))
        else:
            await m.answer(ans)
    except Exception as e:
        await m.answer("Ошибка")
        print(e)

@dp.callback_query(F.data.startswith("buy_") | F.data.startswith("sub_"))
async def pay(c: types.CallbackQuery):
    if c.data == "buy_40":
        t, p, price = "40 сообщений", "msg_40", 25
    elif c.data == "sub_day":
        t, p, price = "День", "sub_day", 70
    else:
        t, p, price = "Неделя", "sub_week", 250
    await bot.send_invoice(c.from_user.id, t, "Покупка", p, "XTR", [LabeledPrice("x", price)])
    await c.answer()

@dp.pre_checkout_query()
async def pre(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def success(m: types.Message):
    p = m.successful_payment.invoice_payload
    u = get_user(m.from_user.id)
    if p.startswith("msg_"):
        u["paid"] += int(p.split("_")[1])
        await m.answer("Добавлено")
    elif p == "sub_day":
        u["subscription_until"] = (datetime.now() + timedelta(days=1)).isoformat()
        await m.answer("Подписка на день")
    elif p == "sub_week":
        u["subscription_until"] = (datetime.now() + timedelta(days=7)).isoformat()
        await m.answer("Подписка на неделю")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
