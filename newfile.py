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
FAL_KEY = "fal_sk_c10eef557ce5484b846ffb9a1ea4b88c:99364bb1c0b177950790787255e8b4f8"
ADMIN_ID = 5044633928

client = OpenAI(api_key=GROK_API_KEY, base_url="https://api.x.ai/v1")
eleven = ElevenLabs(api_key=ELEVEN_API_KEY)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

users = {}

def get_user(uid):
    if uid not in users:
        users[uid] = {"messages": 0, "voice_mode": False, "last_answer": "", "pending_photo": ""}
    return users[uid]

def is_admin(uid):
    return uid == ADMIN_ID

kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📊 Профиль"), KeyboardButton(text="🛒 Магазин")],
    [KeyboardButton(text="🎤 Голосовой режим"), KeyboardButton(text="🖼 Фото")]
], resize_keyboard=True)

def eleven_voice(text: str) -> bytes:
    audio = eleven.text_to_speech.convert(
        text=text[:400],
        voice_id="EXAVITQu4vr4xnSDxMaL",
        model_id="eleven_multilingual_v2"
    )
    return b"".join(audio)

def generate_fal_image(prompt: str) -> str:
    headers = {
        "Authorization": f"Key {FAL_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": prompt,
        "image_size": "portrait_4_3",
        "num_inference_steps": 28,
        "guidance_scale": 3.5
    }
    # Используем модель Flux (хорошо работает с разными промптами)
    r = requests.post(
        "https://fal.run/fal-ai/flux/dev",
        headers=headers,
        json=payload,
        timeout=120
    )
    print("FAL STATUS:", r.status_code)
    print("FAL BODY:", r.text[:300])
    r.raise_for_status()
    return r.json()["images"][0]["url"]

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("Привет, я Алиса.", reply_markup=kb)

@dp.message(F.text == "📊 Профиль")
async def profile(m: types.Message):
    u = get_user(m.from_user.id)
    free = "∞" if is_admin(m.from_user.id) else max(0, 30 - u["messages"])
    await m.answer(f"Бесплатных: {free}\nГолос: {'вкл' if u['voice_mode'] else 'выкл'}")

@dp.message(F.text == "🛒 Магазин")
async def shop(m: types.Message):
    if is_admin(m.from_user.id):
        await m.answer("Для тебя бесплатно")
        return
    await m.answer("Магазин скоро")

@dp.message(F.text == "🎤 Голосовой режим")
async def vmode(m: types.Message):
    u = get_user(m.from_user.id)
    u["voice_mode"] = not u["voice_mode"]
    await m.answer("Голос " + ("вкл" if u["voice_mode"] else "выкл"))

@dp.message(F.text == "🖼 Фото")
async def photo_btn(m: types.Message):
    await m.answer("Напиши описание фото")

@dp.message(F.text)
async def handler(m: types.Message):
    text = m.text.strip()
    uid = m.from_user.id
    u = get_user(uid)
    admin = is_admin(uid)

    if text.lower().startswith(("фото", "в ", "на ", "картин")):
        u["pending_photo"] = text
        if admin:
            await m.answer("Генерирую...")
            try:
                url = generate_fal_image(f"beautiful young woman, {text}, highly detailed, photorealistic")
                await m.answer_photo(url)
            except Exception as e:
                await m.answer("Ошибка генерации")
                print(e)
        else:
            ikb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить 50⭐", callback_data="pay_photo")]
            ])
            await m.answer("Сгенерировать за 50⭐?", reply_markup=ikb)
        return

    if not admin and u["messages"] >= 30:
        await m.answer("Лимит сообщений")
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
                    [InlineKeyboardButton(text="Голос 10⭐", callback_data="pay_voice")]
                ])
                await m.answer(answer, reply_markup=ikb)
        else:
            await m.answer(answer)
    except Exception as e:
        await m.answer("Ошибка")
        print(e)

@dp.callback_query(F.data == "pay_photo")
async def pay_photo(c: types.CallbackQuery):
    await bot.send_invoice(c.from_user.id, "Фото", "Генерация", "photo", "XTR", [LabeledPrice("Фото", 50)])
    await c.answer()

@dp.callback_query(F.data == "pay_voice")
async def pay_voice(c: types.CallbackQuery):
    await bot.send_invoice(c.from_user.id, "Голос", "Ответ", "voice", "XTR", [LabeledPrice("Голос", 10)])
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
            url = generate_fal_image(u.get("pending_photo", "beautiful woman"))
            await m.answer_photo(url)
        except Exception as e:
            await m.answer("Ошибка фото")
            print(e)
    elif p == "voice":
        try:
            audio = eleven_voice(u.get("last_answer", "Привет"))
            await m.answer_voice(BufferedInputFile(audio, "v.mp3"))
        except Exception as e:
            await m.answer("Ошибка голоса")
            print(e)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
