# ============================================================
#  utils/keyboards.py — клавиатуры
# ============================================================

from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)


def main_menu() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="👤 Мой Профиль"),  KeyboardButton(text="🏆 ТОП")],
        [KeyboardButton(text="⚒ Биржа Труда"),   KeyboardButton(text="🎰 Казино")],
        [KeyboardButton(text="🔫 Банды"),         KeyboardButton(text="📊 Рейтинг Банд")],
        [KeyboardButton(text="🤝 Рефералы"),      KeyboardButton(text="🎁 Промокод")],
        [KeyboardButton(text="⚡️ Майнинг"),      KeyboardButton(text="📜 Квесты")],
        [KeyboardButton(text="⚙️ Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def back_btn(text: str, callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔙 {text}", callback_data=callback)]
    ])
