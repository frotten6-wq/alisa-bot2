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
            "photo_prompt": "",
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

def gen_image(prompt: str) -> str:
    r = requests.post(
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
    print("IMG:", r.status_code, r.text[:150])
    r.raise_for_status()
    return r.json()["data"][0]["url"]

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("Привет. Я Алиса.", reply_markup=main_kb)

@dp.message(Command("users"))
async def cmd_users(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    if not users:
        await m.answer("Нет пользователей")
        return
    text = "\n".join([f"{uid} | {u['messages']} сообщ" for uid, u in list(users.items())[:20]])
    await m.answer("Пользователи:\n" + text + "\n\n/user ID")

@dp.message(Command("user"))
async def cmd_user(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    try:
        uid = int(m.text.split()[1])
        u = users[uid]
        await m.answer(f"ID: {uid}\nСообщений: {u['messages']}\nОтношения: {u['relationship']}\n/history {uid}")
    except:
        await m.answer("Не найден")

@dp.message(Command("history"))
async def cmd_history(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    try:
        uid = int(m.text.split()[1])
        hist = users[uid]["history"][-10:]
        text = "\n".join([f"{h['role']}: {h['content'][:80]}" for h in hist])
        await m.answer(text or "Пусто")
    except:
        await m.answer("Нет истории")

@dp.message(F.text == "📊 Профиль")
async def profile(m: types.Message):
    u = get_user(m.from_user.id)
    free = "∞" if is_admin(m.from_user.id) or has_sub(u) else max(0, 30 - u["messages"])
    await m.answer(f"Отношения: {rel_text(u['relationship'])}\nБесплатных: {free}\nПлатных: {u['paid']}")

@dp.message(F.text == "🎭 Сценарии")
async def scenarios(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Вечер", callback_data="sc_evening")],
        [InlineKeyboardButton(text="Откровенно", callback_data="sc_spicy")],
        [InlineKeyboardButton(text="Убрать", callback_data="sc_none")]
    ])
    await m.answer("Сценарий:", reply_markup=kb)

@dp.message(F.text == "🛒 Магазин")
async def shop(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="40 сообщений — 25⭐", callback_data="buy_40")],
        [InlineKeyboardButton(text="День — 70⭐", callback_data="sub_day")]
    ])
    await m.answer("Магазин:", reply_markup=kb)

@dp.message(F.text == "🎁 Бонус")
async def bonus(m: types.Message):
    u = get_user(m.from_user.id)
    now = datetime.now()
    if u["bonus_claimed"] and now - datetime.fromisoformat(u["bonus_claimed"]) < timedelta(hours=20):
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
    await m.answer("Напиши: Фото описание")

@dp.callback_query(F.data.startswith("sc_"))
async def set_sc(c: types.CallbackQuery):
    key = c.data.split("_")[1]
    get_user(c.from_user.id)["scenario"] = None if key == "none" else key
    await c.answer("Готово")

@dp.message(F.text)
async def chat(m: types.Message):
    text = m.text.strip()
    uid = m.from_user.id
    u = get_user(uid)
    admin = is_admin(uid)

    # ===== ФОТО =====
    if text.lower().startswith("фото"):
        prompt = text[4:].strip() or "красивая девушка"
        u["photo_prompt"] = prompt
        if admin or has_sub(u):
            await m.answer("Генерирую...")
            try:
                url = gen_image(f"beautiful young woman, {prompt}, photorealistic")
                await m.answer_photo(url)
            except Exception as e:
                await m.answer("Ошибка генерации")
                print(e)
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="50⭐", callback_data="pay_photo")]
            ])
            await m.answer("Сгенерировать фото?", reply_markup=kb)
        return

    # Лимит
    if not admin and not has_sub(u) and u["messages"] >= 30 and u["paid"] <= 0:
        await m.answer("Лимит сообщений")
        return

    if not admin and not has_sub(u):
        if u["messages"] < 30:
            u["messages"] += 1
        else:
            u["paid"] -= 1

    u["relationship"] = min(100, u["relationship"] + 1)
    u["history"].append({"role": "user", "content": text})
    if len(u["history"]) > 12:
        u["history"] = u["history"][-12:]

    await bot.send_chat_action(m.chat.id, "typing")

    system = "Ты Алиса, 23 года. Живая, естественная. Отвечай по ситуации и разнообразно."
    try:
        r = client.chat.completions.create(
            model="grok-4",
            messages=[{"role": "system", "content": system}] + u["history"],
            temperature=0.87
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

@dp.callback_query(F.data == "pay_photo")
async def pay_photo(c: types.CallbackQuery):
    await bot.send_invoice(c.from_user.id, "Фото", "Генерация", "photo", "XTR", [LabeledPrice("Фото", 50)])
    await c.answer()

@dp.callback_query(F.data.startswith("buy_") | F.data.startswith("sub_"))
async def pay_other(c: types.CallbackQuery):
    if "40" in c.data:
        t, p, pr = "40 сообщений", "msg_40", 25
    else:
        t, p, pr = "Подписка", "sub_day", 70
    await bot.send_invoice(c.from_user.id, t, "Покупка", p, "XTR", [LabeledPrice("x", pr)])
    await c.answer()

@dp.pre_checkout_query()
async def pre(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def success(m: types.Message):
    p = m.successful_payment.invoice_payload
    u = get_user(m.from_user.id)
    if p == "photo":
        try:
            url = gen_image(f"beautiful woman, {u.get('photo_prompt', '')}")
            await m.answer_photo(url)
        except:
            await m.answer("Ошибка фото")
    elif p.startswith("msg_"):
        u["paid"] += 40
        await m.answer("Сообщения добавлены")
    elif p.startswith("sub_"):
        u["subscription_until"] = (datetime.now() + timedelta(days=1)).isoformat()
        await m.answer("Подписка активирована")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
