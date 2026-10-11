import os
import asyncio
import edge_tts
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery, FSInputFile
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
            "relationship": 0,
            "name": None,
            "history": []
        }
    return users[uid]

def get_level(p):
    if p < 25: return "знакомство"
    if p < 60: return "флирт"
    return "близкие"

kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📊 Профиль"), KeyboardButton(text="🛒 Магазин")],
    [KeyboardButton(text="🎁 Подарок"), KeyboardButton(text="🖼 Фото от меня")]
], resize_keyboard=True)

async def generate_voice(text: str, filename="voice.mp3"):
    communicate = edge_tts.Communicate(text, "ru-RU-SvetlanaNeural")
    await communicate.save(filename)
    return filename

@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("Привет, я Алиса.\n30 бесплатных сообщений.", reply_markup=kb)

@dp.message(F.text.lower().startswith("меня зовут"))
async def set_name(m: types.Message):
    name = m.text.split(maxsplit=2)[-1].strip()
    get_user(m.from_user.id)["name"] = name
    await m.answer(f"Хорошо, {name}")

@dp.message(F.text == "📊 Профиль")
async def profile(m: types.Message):
    u = get_user(m.from_user.id)
    free = max(0, 30 - u["messages"])
    name = u["name"] or "не знаю"
    await m.answer(f"Имя: {name}\nУровень: {get_level(u['relationship'])}\nБесплатных: {free}\nПлатных: {u['paid']}")

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

@dp.message(F.text == "🖼 Фото от меня")
async def ask_photo(m: types.Message):
    await m.answer("Напиши, какое фото хочешь. Стоит 50⭐\nПример: «фото в белье на кровати»")

@dp.message(F.text.lower().startswith("фото "))
async def generate_photo(m: types.Message):
    u = get_user(m.from_user.id)
    if u["paid"] < 50:
        await m.answer("Генерация фото — 50⭐")
        return
    u["paid"] -= 50
    prompt = m.text[5:].strip()
    await m.answer("Генерирую...")
    try:
        # Заглушка под генерацию (xAI image пока через отдельный endpoint)
        # Позже можно заменить на реальный вызов
        await m.answer(f"Фото по запросу: {prompt}\n(генерация изображений скоро будет подключена полностью)")
    except:
        await m.answer("Не получилось сгенерировать")

@dp.message(F.text)
async def chat(m: types.Message):
    u = get_user(m.from_user.id)
    if u["messages"] >= 30 and u["paid"] <= 0:
        await m.answer("Бесплатные закончились")
        return
    if u["messages"] < 30:
        u["messages"] += 1
    else:
        u["paid"] -= 1
    u["relationship"] = min(100, u["relationship"] + 1)

    u["history"].append({"role": "user", "content": m.text})
    if len(u["history"]) > 8:
        u["history"] = u["history"][-8:]

    await bot.send_chat_action(m.chat.id, "typing")
    await asyncio.sleep(0.8)

    name_part = f" Пользователя зовут {u['name']}." if u["name"] else ""
    system = (
        "Ты Алиса, 23 года. Живая, с характером и лёгким юмором. "
        "Поддерживаешь разговор, иногда сама задаёшь вопросы или проявляешь инициативу. "
        "Если пишут обычно — интересно общаешься. Если откровенно — подстраиваешься. "
        "Эмодзи почти не используй."
        + name_part + f" Стадия: {get_level(u['relationship'])}."
    )

    messages = [{"role": "system", "content": system}] + u["history"]
    try:
        r = client.chat.completions.create(model="grok-4", messages=messages, temperature=0.87)
        answer = r.choices[0].message.content
        u["history"].append({"role": "assistant", "content": answer})

        # Иногда отвечает голосовым
        if len(answer) < 180 and u["paid"] >= 0:
            try:
                filename = f"voice_{m.from_user.id}.mp3"
                await generate_voice(answer, filename)
                await m.answer_voice(FSInputFile(filename))
                os.remove(filename)
                return
            except:
                pass
        await m.answer(answer)
    except:
        await m.answer("Секунду...")

@dp.message(F.photo)
async def photo_react(m: types.Message):
    u = get_user(m.from_user.id)
    if u["paid"] < 25:
        await m.answer("Реакция на фото — 25⭐")
        return
    u["paid"] -= 25
    await m.answer("Смотрю... интересно. Расскажи подробнее?")

@dp.message(F.voice)
async def voice_in(m: types.Message):
    u = get_user(m.from_user.id)
    if u["paid"] < 15:
        await m.answer("Прослушивание голосового — 15⭐")
        return
    u["paid"] -= 15
    await m.answer("Слышу тебя.")

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
async def success_pay(m: types.Message):
    p = m.successful_payment.invoice_payload
    u = get_user(m.from_user.id)
    if p.startswith("buy_"):
        u["paid"] += int(p.split("_")[1])
        await m.answer("Сообщения добавлены")
    else:
        u["relationship"] = min(100, u["relationship"] + int(p.split("_")[1]))
        await m.answer("Спасибо за подарок")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
