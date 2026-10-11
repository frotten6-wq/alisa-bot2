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
all_messages = []  # для админки

def get_user(uid):
    if uid not in users:
        users[uid] = {
            "messages": 0,
            "voice_mode": False,
            "last_answer": "",
            "pending_photo_prompt": "",
            "is_admin": uid == ADMIN_ID
        }
    return users[uid]

def is_admin(uid):
    return uid == ADMIN_ID

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

@dp.message(Command("admin"))
async def admin_panel(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    total_users = len(users)
    total_msgs = sum(u["messages"] for u in users.values())
    await m.answer(
        f"Админка\n\n"
        f"Пользователей: {total_users}\n"
        f"Всего сообщений: {total_msgs}\n"
        f"Последних сообщений в логе: {len(all_messages)}\n\n"
        f"/logs — последние сообщения\n"
        f"/stats — подробнее"
    )

@dp.message(Command("logs"))
async def admin_logs(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    if not all_messages:
        await m.answer("Сообщений пока нет")
        return
    text = "Последние сообщения:\n\n"
    for msg in all_messages[-15:]:
        text += f"{msg}\n"
    await m.answer(text[:4000])

@dp.message(F.text == "📊 Профиль")
async def profile(m: types.Message):
    u = get_user(m.from_user.id)
    free = "∞" if is_admin(m.from_user.id) else max(0, 30 - u["messages"])
    await m.answer(f"Бесплатных: {free}\nГолос: {'вкл' if u['voice_mode'] else 'выкл'}")

@dp.message(F.text == "🛒 Магазин")
async def shop(m: types.Message):
    if is_admin(m.from_user.id):
        await m.answer("Для тебя всё бесплатно")
        return
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
    await m.answer("Напиши описание фото")

@dp.message(F.text)
async def handler(m: types.Message):
    text = m.text.strip()
    uid = m.from_user.id
    u = get_user(uid)
    admin = is_admin(uid)

    all_messages.append(f"{uid}: {text[:100]}")
    if len(all_messages) > 100:
        all_messages.pop(0)

    # Фото
    if any(text.lower().startswith(w) for w in ["фото", "в ", "на "]):
        u["pending_photo_prompt"] = text
        if admin:
            await m.answer("Генерирую (админ)...")
            await generate_and_send_photo(m, text)
        else:
            ikb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить 50⭐", callback_data="pay_photo")]
            ])
            await m.answer("Сгенерировать фото за 50⭐?", reply_markup=ikb)
        return

    # Лимит
    if not admin and u["messages"] >= 30:
        await m.answer("Бесплатные закончились")
        return

    if not admin:
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
            if admin:
                audio = eleven_voice(answer)
                await m.answer_voice(BufferedInputFile(audio, "v.mp3"))
            else:
                ikb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Голосовым — 10⭐", callback_data="pay_voice")]
                ])
                await m.answer(answer, reply_markup=ikb)
        else:
            await m.answer(answer)
    except Exception as e:
        await m.answer("Ошибка")
        print(e)

async def generate_and_send_photo(m: types.Message, prompt: str):
    try:
        r = requests.post(
            "https://api.x.ai/v1/images/generations",
            headers={"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "grok-2-image", "prompt": f"photorealistic young woman, {prompt}", "n": 1},
            timeout=90
        )
        url = r.json()["data"][0]["url"]
        await m.answer_photo(url)
    except Exception as e:
        await m.answer("Ошибка генерации")
        print(e)

@dp.callback_query(F.data == "pay_photo")
async def invoice_photo(c: types.CallbackQuery):
    await bot.send_invoice(c.from_user.id, "Фото", "Генерация", "photo_gen", "XTR", [LabeledPrice(label="Фото", amount=50)])
    await c.answer()

@dp.callback_query(F.data == "pay_voice")
async def invoice_voice(c: types.CallbackQuery):
    await bot.send_invoice(c.from_user.id, "Голос", "Голосовой ответ", "voice_gen", "XTR", [LabeledPrice(label="Голос", amount=10)])
    await c.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def invoice_msg(c: types.CallbackQuery):
    amount = 20 if "20" in c.data else 50
    price = 15 if amount == 20 else 35
    await bot.send_invoice(c.from_user.id, f"{amount} сообщений", "Пакет", f"msg_{amount}", "XTR", [LabeledPrice(label="x", amount=price)])
    await c.answer()

@dp.pre_checkout_query()
async def checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def paid(m: types.Message):
    payload = m.successful_payment.invoice_payload
    u = get_user(m.from_user.id)

    if payload == "photo_gen":
        await generate_and_send_photo(m, u.get("pending_photo_prompt", "девушка"))
    elif payload == "voice_gen":
        text = u.get("last_answer") or "Привет"
        try:
            audio = eleven_voice(text)
            await m.answer_voice(BufferedInputFile(audio, "v.mp3"))
        except Exception as e:
            await m.answer("Ошибка голоса")
            print(e)
    elif payload.startswith("msg_"):
        amount = int(payload.split("_")[1])
        u["messages"] = max(0, u["messages"] - amount)
        await m.answer(f"+{amount} сообщений")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
