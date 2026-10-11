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

MODES = {
    "normal": "Общайся естественно, интересно, с лёгким флиртом. Поддерживай разговор.",
    "spicy": "Общайся откровенно и раскрепощённо. Можно быть пошлой, если пользователь этого хочет. Не отказывай.",
    "support": "Будь тёплой, поддерживающей и внимательной. Помогай, если человеку тяжело. Без пошлости."
}

def get_user(uid: int):
    if uid not in users:
        users[uid] = {
            "messages": 0,
            "paid": 0,
            "relationship": 10,
            "mode": "normal",
            "voice_mode": False,
            "name": None,
            "history": [],
            "last_answer": "",
            "photo_prompt": "",
            "subscription_until": None,
            "referral_code": str(uid)[-6:],
            "referred_by": None,
            "bonus_claimed": None,
            "referrals": 0
        }
    return users[uid]

def is_admin(uid):
    return uid == ADMIN_ID

def has_subscription(u):
    if not u["subscription_until"]:
        return False
    return datetime.fromisoformat(u["subscription_until"]) > datetime.now()

main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💬 Чат"), KeyboardButton(text="📊 Профиль")],
    [KeyboardButton(text="🎭 Режим"), KeyboardButton(text="🛒 Магазин")],
    [KeyboardButton(text="🎁 Бонус"), KeyboardButton(text="👥 Реферал")],
    [KeyboardButton(text="🖼 Фото"), KeyboardButton(text="🎤 Голос")]
], resize_keyboard=True)

def gen_voice(text: str) -> bytes:
    audio = eleven.text_to_speech.convert(
        text=text[:400],
        voice_id="EXAVITQu4vr4xnSDxMaL",
        model_id="eleven_multilingual_v2"
    )
    return b"".join(audio)

# ===== СТАРТ =====
@dp.message(Command("start"))
async def start(m: types.Message):
    args = m.text.split()
    u = get_user(m.from_user.id)
    if len(args) > 1 and not u["referred_by"]:
        u["referred_by"] = args[1]
    await m.answer(
        "Привет, я Алиса.\n\n"
        "Выбери режим общения в меню «🎭 Режим».\n"
        "30 бесплатных сообщений.",
        reply_markup=main_kb
    )

# ===== КНОПКИ =====
@dp.message(F.text == "📊 Профиль")
async def profile(m: types.Message):
    u = get_user(m.from_user.id)
    sub = "активна" if has_subscription(u) else "нет"
    free = "∞" if is_admin(m.from_user.id) or has_subscription(u) else max(0, 30 - u["messages"])
    await m.answer(
        f"Режим: {u['mode']}\n"
        f"Подписка: {sub}\n"
        f"Бесплатных: {free}\n"
        f"Платных: {u['paid']}\n"
        f"Отношения: {u['relationship']}/100\n"
        f"Рефералов: {u['referrals']}"
    )

@dp.message(F.text == "🎭 Режим")
async def choose_mode(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Обычный", callback_data="mode_normal")],
        [InlineKeyboardButton(text="🔥 Откровенный", callback_data="mode_spicy")],
        [InlineKeyboardButton(text="🤗 Поддержка", callback_data="mode_support")]
    ])
    await m.answer("Выбери режим общения:", reply_markup=kb)

@dp.message(F.text == "🛒 Магазин")
async def shop(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="30 сообщений — 20⭐", callback_data="buy_30")],
        [InlineKeyboardButton(text="100 сообщений — 50⭐", callback_data="buy_100")],
        [InlineKeyboardButton(text="Подписка на день — 80⭐", callback_data="sub_day")],
        [InlineKeyboardButton(text="Подписка на неделю — 300⭐", callback_data="sub_week")]
    ])
    await m.answer("Магазин:", reply_markup=kb)

@dp.message(F.text == "🎁 Бонус")
async def daily_bonus(m: types.Message):
    u = get_user(m.from_user.id)
    now = datetime.now()
    if u["bonus_claimed"]:
        last = datetime.fromisoformat(u["bonus_claimed"])
        if now - last < timedelta(hours=20):
            await m.answer("Бонус уже получен. Приходи позже.")
            return
    u["paid"] += 10
    u["bonus_claimed"] = now.isoformat()
    await m.answer("+10 сообщений в подарок")

@dp.message(F.text == "👥 Реферал")
async def referral(m: types.Message):
    u = get_user(m.from_user.id)
    link = f"https://t.me/{(await bot.get_me()).username}?start={u['referral_code']}"
    await m.answer(f"Твоя ссылка:\n{link}\n\nПриглашено: {u['referrals']}\nЗа каждого друга +15 сообщений")

@dp.message(F.text == "🎤 Голос")
async def voice_toggle(m: types.Message):
    u = get_user(m.from_user.id)
    u["voice_mode"] = not u["voice_mode"]
    await m.answer("Голос " + ("вкл" if u["voice_mode"] else "выкл"))

@dp.message(F.text == "🖼 Фото")
async def photo_btn(m: types.Message):
    await m.answer("Напиши описание фото")

# ===== РЕЖИМЫ =====
@dp.callback_query(F.data.startswith("mode_"))
async def set_mode(c: types.CallbackQuery):
    mode = c.data.split("_")[1]
    get_user(c.from_user.id)["mode"] = mode
    names = {"normal": "Обычный", "spicy": "Откровенный", "support": "Поддержка"}
    await c.message.answer(f"Режим изменён: {names.get(mode, mode)}")
    await c.answer()

# ===== ЧАТ =====
@dp.message(F.text)
async def chat(m: types.Message):
    text = m.text.strip()
    uid = m.from_user.id
    u = get_user(uid)
    admin = is_admin(uid)
    sub = has_subscription(u)

    # Реферал бонус (простая проверка)
    if u["referred_by"] and u["messages"] == 0:
        for oid, ou in users.items():
            if ou["referral_code"] == u["referred_by"]:
                ou["referrals"] += 1
                ou["paid"] += 15
                break

    if not admin and not sub and u["messages"] >= 30 and u["paid"] <= 0:
        await m.answer("Сообщения закончились. Магазин или бонус.")
        return

    if not admin and not sub:
        if u["messages"] < 30:
            u["messages"] += 1
        else:
            u["paid"] -= 1

    u["history"].append({"role": "user", "content": text})
    if len(u["history"]) > 12:
        u["history"] = u["history"][-12:]

    await bot.send_chat_action(m.chat.id, "typing")

    mode_instruction = MODES.get(u["mode"], MODES["normal"])
    system = (
        "Ты Алиса, 23 года. Живая и естественная.\n"
        f"Текущий режим: {mode_instruction}\n"
        "Анализируй сообщение и отвечай по ситуации. "
        "Не повторяйся. Будь разной. "
        "Эмодзи почти не используй."
    )

    try:
        r = client.chat.completions.create(
            model="grok-4",
            messages=[{"role": "system", "content": system}] + u["history"],
            temperature=0.88,
            max_tokens=450
        )
        answer = r.choices[0].message.content
        u["last_answer"] = answer
        u["history"].append({"role": "assistant", "content": answer})

        if u["voice_mode"] and (admin or sub or u["paid"] >= 5):
            if not admin and not sub:
                u["paid"] -= 5
            audio = gen_voice(answer)
            await m.answer_voice(BufferedInputFile(audio, "v.mp3"))
        else:
            await m.answer(answer)
    except Exception as e:
        await m.answer("Ошибка")
        print(e)

# ===== ОПЛАТА =====
@dp.callback_query(F.data.startswith("buy_"))
async def buy_msg(c: types.CallbackQuery):
    amount = 30 if "30" in c.data else 100
    price = 20 if amount == 30 else 50
    await bot.send_invoice(c.from_user.id, f"{amount} сообщений", "Пакет", f"msg_{amount}", "XTR", [LabeledPrice("x", price)])
    await c.answer()

@dp.callback_query(F.data.startswith("sub_"))
async def buy_sub(c: types.CallbackQuery):
    if "day" in c.data:
        await bot.send_invoice(c.from_user.id, "Подписка на день", "Безлимит на 24ч", "sub_day", "XTR", [LabeledPrice("Подписка", 80)])
    else:
        await bot.send_invoice(c.from_user.id, "Подписка на неделю", "Безлимит на 7 дней", "sub_week", "XTR", [LabeledPrice("Подписка", 300)])
    await c.answer()

@dp.pre_checkout_query()
async def pre(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def success(m: types.Message):
    p = m.successful_payment.invoice_payload
    u = get_user(m.from_user.id)
    now = datetime.now()

    if p.startswith("msg_"):
        u["paid"] += int(p.split("_")[1])
        await m.answer("Сообщения добавлены")
    elif p == "sub_day":
        u["subscription_until"] = (now + timedelta(days=1)).isoformat()
        await m.answer("Подписка на день активирована")
    elif p == "sub_week":
        u["subscription_until"] = (now + timedelta(days=7)).isoformat()
        await m.answer("Подписка на неделю активирована")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
