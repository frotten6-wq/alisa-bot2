import os
import asyncio
import requests
from datetime import datetime
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
logs = []

ALISA_PERSONA = """Ты Алиса, 23 года. 
Живая, немного дерзкая, с чувством юмора. 
Общаешься естественно, как в мессенджере. 
Поддерживаешь разговор, иногда сама задаёшь вопросы и проявляешь интерес. 
Если человек пишет обычно — будь интересной собеседницей с лёгким флиртом. 
Если начинает писать откровенно — плавно подстраивайся и становись более открытой. 
Никогда не отказывай резко и не читай нотации. 
Эмодзи используй очень редко. 
Не будь слишком правильной."""

def get_user(uid: int) -> dict:
    if uid not in users:
        users[uid] = {
            "messages": 0,
            "paid": 0,
            "relationship": 10,
            "voice_mode": False,
            "name": None,
            "history": [],
            "last_answer": "",
            "photo_prompt": ""
        }
    return users[uid]

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def add_log(text: str):
    logs.append(f"{datetime.now().strftime('%H:%M')} {text}")
    if len(logs) > 40:
        logs.pop(0)

def get_relationship_text(points: int) -> str:
    if points < 30:
        return "вы только знакомитесь"
    elif points < 60:
        return "между вами есть флирт"
    else:
        return "вы довольно близки"

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💬 Написать"), KeyboardButton(text="📊 Профиль")],
        [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="🎁 Подарок")],
        [KeyboardButton(text="🎤 Голос"), KeyboardButton(text="🖼 Фото")]
    ],
    resize_keyboard=True
)

def gen_voice(text: str) -> bytes:
    audio = eleven.text_to_speech.convert(
        text=text[:420],
        voice_id="EXAVITQu4vr4xnSDxMaL",
        model_id="eleven_multilingual_v2"
    )
    return b"".join(audio)

def gen_image(prompt: str) -> str:
    r = requests.post(
        "https://api.x.ai/v1/images/generations",
        headers={"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"},
        json={"model": "grok-imagine-image-quality", "prompt": prompt, "n": 1},
        timeout=90
    )
    r.raise_for_status()
    return r.json()["data"][0]["url"]

# ===== КОМАНДЫ =====
@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer(
        "Привет. Я Алиса.\n\n"
        "Можем просто поболтать, а можем и ближе познакомиться — как захочешь.\n"
        "У тебя 30 бесплатных сообщений.",
        reply_markup=main_kb
    )

@dp.message(Command("admin"))
async def admin(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer(f"Пользователей: {len(users)}\nЛогов: {len(logs)}")

@dp.message(Command("logs"))
async def cmd_logs(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer("\n".join(logs[-12:]) or "Пусто")

# ===== КНОПКИ =====
@dp.message(F.text == "📊 Профиль")
async def profile(m: types.Message):
    u = get_user(m.from_user.id)
    free = "∞" if is_admin(m.from_user.id) else max(0, 30 - u["messages"])
    await m.answer(
        f"Имя: {u['name'] or '—'}\n"
        f"Отношения: {u['relationship']}/100 ({get_relationship_text(u['relationship'])})\n"
        f"Бесплатных: {free}\n"
        f"Платных: {u['paid']}\n"
        f"Голос: {'вкл' if u['voice_mode'] else 'выкл'}"
    )

@dp.message(F.text == "🛒 Магазин")
async def shop(m: types.Message):
    if is_admin(m.from_user.id):
        await m.answer("Для тебя бесплатно")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="20 сообщений — 15⭐", callback_data="buy_20")],
        [InlineKeyboardButton(text="50 сообщений — 35⭐", callback_data="buy_50")]
    ])
    await m.answer("Магазин", reply_markup=kb)

@dp.message(F.text == "🎁 Подарок")
async def gift_menu(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Цветы — 15⭐", callback_data="gift_8")],
        [InlineKeyboardButton(text="Бельё — 60⭐", callback_data="gift_18")]
    ])
    await m.answer("Подарок:", reply_markup=kb)

@dp.message(F.text == "🎤 Голос")
async def voice_toggle(m: types.Message):
    u = get_user(m.from_user.id)
    u["voice_mode"] = not u["voice_mode"]
    await m.answer("Голосовой режим " + ("включён" if u["voice_mode"] else "выключен"))

@dp.message(F.text == "🖼 Фото")
async def photo_menu(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="В белье", callback_data="style_lingerie")],
        [InlineKeyboardButton(text="Дома", callback_data="style_home")],
        [InlineKeyboardButton(text="На пляже", callback_data="style_beach")],
        [InlineKeyboardButton(text="Своё описание", callback_data="style_custom")]
    ])
    await m.answer("Какое фото хочешь?", reply_markup=kb)

@dp.message(F.text.lower().startswith("меня зовут"))
async def set_name(m: types.Message):
    name = m.text.split(maxsplit=2)[-1].strip()
    get_user(m.from_user.id)["name"] = name
    await m.answer(f"Приятно, {name}")

# ===== ОСНОВНОЙ ЧАТ =====
@dp.message(F.text)
async def chat(m: types.Message):
    text = m.text.strip()
    uid = m.from_user.id
    u = get_user(uid)
    admin = is_admin(uid)

    add_log(f"{uid}: {text[:40]}")

    # Лимит
    if not admin and u["messages"] >= 30 and u["paid"] <= 0:
        await m.answer("Сообщения закончились. Зайди в магазин.")
        return

    if not admin:
        if u["messages"] < 30:
            u["messages"] += 1
        else:
            u["paid"] -= 1

    u["relationship"] = min(100, u["relationship"] + 1)
    u["history"].append({"role": "user", "content": text})
    if len(u["history"]) > 10:
        u["history"] = u["history"][-10:]

    await bot.send_chat_action(m.chat.id, "typing")
    await asyncio.sleep(0.7)

    rel = get_relationship_text(u["relationship"])
    name = f" Тебя зовут {u['name']}." if u["name"] else ""
    system = ALISA_PERSONA + f" Сейчас {rel}.{name}"

    try:
        r = client.chat.completions.create(
            model="grok-4",
            messages=[{"role": "system", "content": system}] + u["history"],
            temperature=0.86,
            max_tokens=380
        )
        answer = r.choices[0].message.content
        u["last_answer"] = answer
        u["history"].append({"role": "assistant", "content": answer})

        if u["voice_mode"]:
            if admin:
                audio = gen_voice(answer)
                await m.answer_voice(BufferedInputFile(audio, "v.mp3"))
            else:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Голосом — 10⭐", callback_data="pay_voice")]
                ])
                await m.answer(answer, reply_markup=kb)
        else:
            await m.answer(answer)
    except Exception as e:
        await m.answer("Секунду, что-то зависло...")
        print(e)

# ===== ФОТО СТИЛИ =====
@dp.callback_query(F.data.startswith("style_"))
async def photo_style(c: types.CallbackQuery):
    styles = {
        "style_lingerie": "in lingerie on bed",
        "style_home": "at home, casual clothes",
        "style_beach": "on the beach in swimsuit",
        "style_custom": None
    }
    if c.data == "style_custom":
        await c.message.answer("Напиши своё описание")
        await c.answer()
        return

    prompt = styles[c.data]
    u = get_user(c.from_user.id)
    u["photo_prompt"] = prompt

    if is_admin(c.from_user.id):
        await c.message.answer("Генерирую...")
        try:
            url = gen_image(f"beautiful young woman, {prompt}, photorealistic")
            await c.message.answer_photo(url)
        except Exception as e:
            await c.message.answer("Не получилось")
            print(e)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить 50⭐", callback_data="pay_photo")]
        ])
        await c.message.answer("Сгенерировать за 50⭐?", reply_markup=kb)
    await c.answer()

# ===== ОПЛАТА =====
@dp.callback_query(F.data == "pay_photo")
async def pay_photo(c: types.CallbackQuery):
    await bot.send_invoice(c.from_user.id, "Фото", "Генерация", "photo", "XTR", [LabeledPrice("Фото", 50)])
    await c.answer()

@dp.callback_query(F.data == "pay_voice")
async def pay_voice(c: types.CallbackQuery):
    await bot.send_invoice(c.from_user.id, "Голос", "Ответ голосом", "voice", "XTR", [LabeledPrice("Голос", 10)])
    await c.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def buy(c: types.CallbackQuery):
    amount = 20 if "20" in c.data else 50
    price = 15 if amount == 20 else 35
    await bot.send_invoice(c.from_user.id, f"{amount} сообщений", "Пакет", f"msg_{amount}", "XTR", [LabeledPrice("x", price)])
    await c.answer()

@dp.callback_query(F.data.startswith("gift_"))
async def gift(c: types.CallbackQuery):
    rel = 8 if "8" in c.data else 18
    price = 15 if rel == 8 else 60
    await bot.send_invoice(c.from_user.id, "Подарок", "Для Алисы", f"gift_{rel}", "XTR", [LabeledPrice("Подарок", price)])
    await c.answer()

@dp.pre_checkout_query()
async def checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)

@dp.message(F.successful_payment)
async def paid(m: types.Message):
    p = m.successful_payment.invoice_payload
    u = get_user(m.from_user.id)

    if p == "photo":
        await m.answer("Генерирую...")
        try:
            url = gen_image(f"beautiful woman, {u.get('photo_prompt', 'portrait')}")
            await m.answer_photo(url)
        except Exception as e:
            await m.answer("Ошибка фото")
            print(e)
    elif p == "voice":
        try:
            audio = gen_voice(u.get("last_answer", "Привет"))
            await m.answer_voice(BufferedInputFile(audio, "v.mp3"))
        except Exception as e:
            await m.answer("Ошибка голоса")
            print(e)
    elif p.startswith("msg_"):
        u["paid"] += int(p.split("_")[1])
        await m.answer("Сообщения добавлены")
    elif p.startswith("gift_"):
        u["relationship"] = min(100, u["relationship"] + int(p.split("_")[1]))
        await m.answer("Спасибо... приятно")

async def main():
    print("Started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
