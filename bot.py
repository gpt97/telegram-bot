import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties

API_TOKEN = '7966119362:AAE7fdqi5IhJbCRrOGSSWC2YSuS0qtD8lIE'

ADMIN_ID = 713419084  # твой Telegram ID (проверено через /me)

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Каталог товаров
from pathlib import Path
import json

def load_catalog():
    catalog_file = Path("catalog.json")
    if catalog_file.exists():
        with open(catalog_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []



user_carts = {}  # словарь: user_id → список выбранных товаров
user_states = {}  # user_id -> состояние ('wait_name', 'wait_address', и т.п.)
adding_state = {}  # user_id → временные данные добавления товара
user_orders = {}  # временное хранилище заказа: user_id -> {'name': ..., 'address': ...}
    
    
@dp.message(Command("start"))
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Каталог", callback_data="menu_catalog")],
        [InlineKeyboardButton(text="🧺 Корзина", callback_data="menu_cart")],
        [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="menu_clear")],
        [InlineKeyboardButton(text="📋 Мои заказы", callback_data="menu_myorders")]
    ])
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=kb)


@dp.message(Command("catalog"))
async def show_categories(message: Message):
    catalog_data = load_catalog()
    if not catalog_data:
        await message.answer("📦 Каталог пуст.")
        return

    # Соберём список уникальных категорий
    categories = sorted(set(item.get("category", "Без категории") for item in catalog_data))

    # Сформируем кнопки
    buttons = [[InlineKeyboardButton(text=cat, callback_data=f"category_{cat}")] for cat in categories]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer("🗂 Выберите категорию:", reply_markup=kb)


        
@dp.message(Command("cart"))
async def show_cart(message: Message):
    user_id = message.chat.id
    cart = user_carts.get(user_id, [])

    if not cart:
        await message.answer("🛒 Ваша корзина пуста.")
    else:
        text = "<b>🧺 Ваша корзина:</b>\n\n"
        for i, item in enumerate(cart, 1):
            text += f"{i}. {item['name']} — {item['price']}\n"
        await message.answer(text)
        

@dp.message(Command("clear"))
async def clear_cart(message: Message):
    user_id = message.chat.id
    user_carts[user_id] = []
    await message.answer("🗑 Ваша корзина была очищена.")

@dp.message(Command("order"))
async def start_order(message: Message):
    user_id = message.from_user.id
    cart = user_carts.get(user_id, [])

    if not cart:
        await message.answer("❌ Ваша корзина пуста. Добавьте товары перед оформлением заказа.")
        return

    user_states[user_id] = "wait_name"
    user_orders[user_id] = {}
    await message.answer("📋 Введите ваше имя для оформления заказа:")

@dp.message(~F.text.startswith("/"))
async def handle_order_steps(message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    
    if state == "adding_category":
        new_category = message.text.strip()

        # Загружаем текущий список
        categories_file = Path("categories.json")
        if categories_file.exists():
            with open(categories_file, "r", encoding="utf-8") as f:
                categories = json.load(f)
        else:
            categories = []

        if new_category in categories:
            await message.answer("⚠️ Такая категория уже существует.")
        else:
            categories.append(new_category)
            with open(categories_file, "w", encoding="utf-8") as f:
                json.dump(categories, f, ensure_ascii=False, indent=2)
            await message.answer(f"✅ Категория <b>{new_category}</b> добавлена.", parse_mode="HTML")

        user_states.pop(user_id, None)
        return

    
    if state == "editing_id":
        edit_id = message.text.strip()

        # Загружаем каталог
        catalog_file = Path("catalog.json")
        if catalog_file.exists():
            with open(catalog_file, "r", encoding="utf-8") as f:
                catalog_data = json.load(f)
        else:
            await message.answer("📭 Каталог пуст.")
            return

        # Найдём товар
        item = next((i for i in catalog_data if i["id"] == edit_id), None)
        if not item:
            await message.answer("❌ Товар с таким ID не найден.")
            user_states.pop(user_id, None)
            return

        # Сохраняем временно ID
        adding_state[user_id] = {"id": edit_id}
        user_states[user_id] = "editing_name"
        await message.answer(f"✏️ Введите новое название для <b>{item['name']}</b>:", parse_mode="HTML")
        return
        
    if state == "editing_name":
        adding_state[user_id]["name"] = message.text
        user_states[user_id] = "editing_price"
        await message.answer("💰 Теперь введите новую цену:")
        return
        
    if state == "editing_price":
        adding_state[user_id]["price"] = message.text

        edit_id = adding_state[user_id]["id"]

        catalog_file = Path("catalog.json")
        with open(catalog_file, "r", encoding="utf-8") as f:
            catalog_data = json.load(f)

        for item in catalog_data:
            if item["id"] == edit_id:
                item["name"] = adding_state[user_id]["name"]
                item["price"] = adding_state[user_id]["price"]
                break

        with open(catalog_file, "w", encoding="utf-8") as f:
            json.dump(catalog_data, f, ensure_ascii=False, indent=2)

        await message.answer(f"✅ Товар с ID <code>{edit_id}</code> обновлён!", parse_mode="HTML")

        user_states.pop(user_id, None)
        adding_state.pop(user_id, None)
        return



    
    if state == "deleting_item":
        delete_id = message.text.strip()

        # Загружаем каталог
        catalog_file = Path("catalog.json")
        if catalog_file.exists():
            with open(catalog_file, "r", encoding="utf-8") as f:
                catalog_data = json.load(f)
        else:
            await message.answer("📭 Каталог пуст.")
            return

        new_catalog = [item for item in catalog_data if item["id"] != delete_id]

        if len(new_catalog) == len(catalog_data):
            await message.answer("⚠️ Товар с таким ID не найден.")
        else:
            with open(catalog_file, "w", encoding="utf-8") as f:
                json.dump(new_catalog, f, ensure_ascii=False, indent=2)
            await message.answer(f"✅ Товар с ID <code>{delete_id}</code> удалён.", parse_mode="HTML")

        user_states.pop(user_id, None)
        return


    if state == "adding_name":
        adding_state[user_id]["name"] = message.text
        user_states[user_id] = "adding_price"
        await message.answer("💰 Теперь введите цену товара:")
        return

    adding_state[user_id]["price"] = message.text

    # Загружаем категории
    categories_file = Path("categories.json")
    if categories_file.exists():
        with open(categories_file, "r", encoding="utf-8") as f:
            categories = json.load(f)
    else:
        categories = []

    if not categories:
        await message.answer("⚠️ Нет доступных категорий. Сначала добавьте хотя бы одну через /add_category.")
        user_states.pop(user_id, None)
        adding_state.pop(user_id, None)
        return

    # Кнопки категорий
    buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}")] for cat in categories]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    user_states[user_id] = "awaiting_category"
    await message.answer("🗂 Выберите категорию для товара:", reply_markup=kb)
    return

        

    if state == "wait_name":
        user_orders[user_id]["name"] = message.text
        user_states[user_id] = "wait_address"
        await message.answer("📦 Отлично! Теперь введите адрес доставки:")

    elif state == "wait_address":
        user_orders[user_id]["address"] = message.text
        cart = user_carts.get(user_id, [])
        name = user_orders[user_id]["name"]
        address = user_orders[user_id]["address"]

        # Сформировать сообщение
        text = f"<b>✅ Заказ оформлен!</b>\n\n"
        text += f"<b>Имя:</b> {name}\n"
        text += f"<b>Адрес:</b> {address}\n\n"
        text += "<b>Товары:</b>\n"
        for i, item in enumerate(cart, 1):
            text += f"{i}. {item['name']} — {item['price']}\n"

        # Отправить админу
        if user_id != ADMIN_ID:
            await bot.send_message(
                ADMIN_ID,
                f"📥 Новый заказ от <b>{name}</b>\n"
                f"📍 Адрес: {address}\n\n"
                f"<b>Товары:</b>\n" +
                "\n".join([f"• {item['name']} — {item['price']}" for item in cart]),
                parse_mode="HTML"
            )

        # Сохранение в файл
        from datetime import datetime        
        
        order_data = {
            "user_id": user_id,
            "name": name,
            "address": address,
            "items": cart,
            "timestamp": datetime.now().isoformat()
        }

        orders_file = Path("orders.json")
        if orders_file.exists():
            with open(orders_file, "r", encoding="utf-8") as f:
                all_orders = json.load(f)
        else:
            all_orders = []

        all_orders.append(order_data)

        with open(orders_file, "w", encoding="utf-8") as f:
            json.dump(all_orders, f, ensure_ascii=False, indent=2)

        await message.answer(text)

        # Сброс данных
        user_states.pop(user_id, None)
        user_orders.pop(user_id, None)
        user_carts[user_id] = []


        
@dp.message(Command("myorders"))
async def show_my_orders(message: Message):
    from pathlib import Path
    import json

    user_id = message.from_user.id
    print(f"[DEBUG] Вызван /myorders от user_id={user_id}")  # отладка

    orders_file = Path("orders.json")

    if not orders_file.exists():
        await message.answer("❌ У вас пока нет заказов.")
        return

    try:
        with open(orders_file, "r", encoding="utf-8") as f:
            all_orders = json.load(f)
    except json.JSONDecodeError:
        await message.answer("⚠️ Не удалось прочитать заказы.")
        return

    user_orders_list = [o for o in all_orders if o["user_id"] == user_id]

    print(f"[DEBUG] Найдено заказов: {len(user_orders_list)}")  # отладка

    if not user_orders_list:
        await message.answer("📭 У вас пока нет заказов.")
        return

    response = "<b>📋 Ваши заказы:</b>\n\n"
    for i, order in enumerate(user_orders_list, 1):
        response += f"<b>{i}.</b> {order['name']}, {order['address']}\n"
        for item in order["items"]:
            response += f"• {item['name']} — {item['price']}\n"
        response += "\n"

    await message.answer(response)
    
@dp.message(Command("allorders"))
async def show_all_orders(message: Message):
    from pathlib import Path
    import json

    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 У вас нет доступа к этой команде.")
        return

    orders_file = Path("orders.json")
    if not orders_file.exists():
        await message.answer("❌ Заказов пока нет.")
        return

    try:
        with open(orders_file, "r", encoding="utf-8") as f:
            all_orders = json.load(f)
    except json.JSONDecodeError:
        await message.answer("⚠️ Не удалось прочитать файл заказов.")
        return

    if not all_orders:
        await message.answer("📭 Заказов пока нет.")
        return

    response = "<b>📦 Все заказы:</b>\n\n"
    for i, order in enumerate(all_orders, 1):
        response += f"<b>{i}.</b> {order['name']}, {order['address']} (ID: {order['user_id']})\n"
        for item in order["items"]:
            response += f"• {item['name']} — {item['price']}\n"
        response += "\n"

    await message.answer(response)
    
@dp.message(Command("export"))
async def export_orders(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 У вас нет доступа к этой команде.")
        return

    from openpyxl import Workbook
    from pathlib import Path
    import json

    orders_file = Path("orders.json")
    if not orders_file.exists():
        await message.answer("📭 Заказов пока нет.")
        return

    with open(orders_file, "r", encoding="utf-8") as f:
        orders = json.load(f)

    if not orders:
        await message.answer("📭 Заказов пока нет.")
        return

    # Создаём Excel-файл
    wb = Workbook()
    ws = wb.active
    ws.title = "Заказы"

    # Заголовки
    ws.append(["ID", "Имя", "Адрес", "Товары", "Дата"])

    for order in orders:
        items_str = "\n".join(f"{i['name']} — {i['price']}" for i in order["items"])
        ws.append([
            order["user_id"],
            order["name"],
            order["address"],
            items_str,
            order["timestamp"]
        ])

    # Сохраняем файл
    file_path = Path("orders.xlsx")
    wb.save(file_path)

    # Отправляем файл
    from aiogram.types import FSInputFile

    excel_file = FSInputFile(path=file_path)
    await message.answer_document(excel_file, caption="📄 Заказы экспортированы в Excel")

    # Удаляем файл после отправки (если не хочешь — можно не удалять)
    file_path.unlink()

    
@dp.message(Command("add"))
async def start_add(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 У вас нет доступа к этой команде.")
        return

    adding_state[message.from_user.id] = {}
    user_states[message.from_user.id] = "adding_name"
    await message.answer("✏️ Введите название нового товара:")

@dp.message(Command("delete"))
async def start_delete(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 У вас нет доступа к этой команде.")
        return

    catalog_data = load_catalog()
    if not catalog_data:
        await message.answer("📭 Каталог пуст.")
        return

    # Отправим список с ID
    text = "<b>🗑 Что удалить? Введите ID товара:</b>\n\n"
    for item in catalog_data:
        text += f"ID: <code>{item['id']}</code> — {item['name']} ({item['price']})\n"
    
    user_states[message.from_user.id] = "deleting_item"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("edit"))
async def start_edit(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 У вас нет доступа к этой команде.")
        return

    catalog_data = load_catalog()
    if not catalog_data:
        await message.answer("📭 Каталог пуст.")
        return

    text = "<b>✏️ Что редактировать? Введите ID товара:</b>\n\n"
    for item in catalog_data:
        text += f"ID: <code>{item['id']}</code> — {item['name']} ({item['price']})\n"

    user_states[message.from_user.id] = "editing_id"
    await message.answer(text, parse_mode="HTML")
    
@dp.message(Command("me"))
async def show_user_id(message: Message):
    user_id = message.from_user.id
    await message.answer(f"🆔 Ваш Telegram ID: <code>{user_id}</code>", parse_mode="HTML")

@dp.message(Command("add_category"))
async def start_add_category(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 У вас нет доступа к этой команде.")
        return

    user_states[message.from_user.id] = "adding_category"
    await message.answer("🆕 Введите название новой категории:")




@dp.callback_query(F.data.startswith("buy_"))
async def buy_item(callback: CallbackQuery):
    item_id = callback.data.split("_")[1]
    catalog_data = load_catalog()
    item = next((i for i in catalog_data if i["id"] == item_id), None)


    if item:
        user_id = callback.from_user.id
        user_carts.setdefault(user_id, []).append(item)  # добавим в корзину

        await callback.message.answer(
            f"✅ {callback.from_user.full_name}, добавлено в корзину: <b>{item['name']}</b>"
        )
    await callback.answer()
    
@dp.callback_query(F.data.startswith("category_"))
async def show_items_in_category(callback: CallbackQuery):
    selected_category = callback.data.removeprefix("category_")
    catalog_data = load_catalog()

    # Отфильтруем по категории
    items = [item for item in catalog_data if item.get("category") == selected_category]

    if not items:
        await callback.message.answer("❌ В этой категории пока нет товаров.")
        await callback.answer()
        return

    for item in items:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить", callback_data=f"buy_{item['id']}")]
        ])
        text = f"<b>{item['name']}</b>\nЦена: {item['price']}"
        await callback.message.answer(text, reply_markup=kb)

    await callback.answer()
    
@dp.callback_query(F.data.startswith("menu_"))
async def handle_menu_buttons(callback: CallbackQuery):
    action = callback.data
    user_message = callback.message

    if action == "menu_catalog":
        await show_categories(user_message)
    elif action == "menu_cart":
        await show_cart(user_message)
    elif action == "menu_clear":
        await clear_cart(user_message)
    elif action == "menu_myorders":
        await show_my_orders(user_message)

    await callback.answer()
    
@dp.callback_query(F.data.startswith("cat_"))
async def handle_category_choice(callback: CallbackQuery):
    user_id = callback.from_user.id
    category = callback.data.removeprefix("cat_")

    # Проверим, есть ли нужные данные
    if user_id not in adding_state or "name" not in adding_state[user_id] or "price" not in adding_state[user_id]:
        await callback.message.answer("⚠️ Нет информации о товаре. Попробуйте начать с /add заново.")
        await callback.answer()
        return

    # Загружаем каталог
    catalog_file = Path("catalog.json")
    if catalog_file.exists():
        with open(catalog_file, "r", encoding="utf-8") as f:
            catalog_data = json.load(f)
    else:
        catalog_data = []

    new_id = str(len(catalog_data) + 1)
    new_item = {
        "id": new_id,
        "name": adding_state[user_id]["name"],
        "price": adding_state[user_id]["price"],
        "category": category
    }
    catalog_data.append(new_item)

    with open(catalog_file, "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, ensure_ascii=False, indent=2)

    await callback.message.answer(
        f"✅ Товар <b>{new_item['name']}</b> за <b>{new_item['price']}</b> добавлен в категорию <b>{category}</b>!",
        parse_mode="HTML"
    )

    # Сброс состояний
    user_states.pop(user_id, None)
    adding_state.pop(user_id, None)
    await callback.answer()



async def main():
    print("✅ Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
