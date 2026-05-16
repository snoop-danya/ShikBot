# ============================================================
#  utils/helpers.py — вспомогательные функции
# ============================================================

import json
import time
import logging
import re
import sqlite3
from datetime import datetime
from functools import wraps

from aiogram import types
from aiogram.fsm.context import FSMContext

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
#  JSON-хелперы
# ──────────────────────────────────────────────────────────

def safe_json_loads(raw, default):
    """Безопасная десериализация JSON. Никогда не бросает исключение."""
    if not raw or str(raw).strip() in ('', 'null'):
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default


def safe_json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


# ──────────────────────────────────────────────────────────
#  Форматирование
# ──────────────────────────────────────────────────────────

def fmt(n: int | float) -> str:
    """Форматирует число с пробелами: 1 234 567."""
    if isinstance(n, float):
        return f"{n:,.6f}".replace(',', ' ')
    return f"{int(n):,}".replace(',', ' ')


def medal(pos: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(pos, f"{pos}.")


def progress_bar(current, total, length: int = 5) -> str:
    if total == 0:
        return "░" * length
    pct = min(1.0, current / total)
    filled = round(pct * length)
    return "█" * filled + "░" * (length - filled)


def ts_to_str(ts: int | None, fmt_str: str = '%d.%m.%Y %H:%M') -> str:
    if not ts or ts <= 0:
        return "Никогда"
    return datetime.fromtimestamp(ts).strftime(fmt_str)


# ──────────────────────────────────────────────────────────
#  Валидация
# ──────────────────────────────────────────────────────────

NICK_RE = re.compile(r'^[\w\-]{3,15}$', re.UNICODE)

def validate_nickname(nick: str) -> str | None:
    """Возвращает None если ник валиден, иначе — строку с ошибкой."""
    if len(nick) < 3 or len(nick) > 15:
        return "Ник должен быть от 3 до 15 символов!"
    if not NICK_RE.match(nick):
        return "Ник может содержать только буквы, цифры, _ и -"
    return None


# ──────────────────────────────────────────────────────────
#  Игровая логика
# ──────────────────────────────────────────────────────────

def calculate_mining_income(mining_power: float, btc_price: int) -> dict:
    hourly_btc = (mining_power * 24) / 1_000_000
    hourly_rub  = int(hourly_btc * btc_price)
    daily_rub   = hourly_rub * 24
    return {
        'hourly_btc':  hourly_btc,
        'hourly_rub':  hourly_rub,
        'daily_rub':   daily_rub,
        'weekly_rub':  daily_rub * 7,
        'monthly_rub': daily_rub * 30,
    }


def add_stats(db: sqlite3.Connection, cur: sqlite3.Cursor,
              user_id: int, money: int, exp_gain: int) -> tuple[int, int]:
    """Добавляет деньги и опыт, обрабатывает повышение уровня."""
    row = cur.execute("SELECT exp, level FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return 1, 0

    new_exp, new_lvl = row[0] + exp_gain, row[1]
    if new_exp >= 100:
        new_lvl += 1
        new_exp  = 0
        _add_tx(cur, user_id, 0, 'level_up', f'Повышение до уровня {new_lvl}')

    cur.execute(
        "UPDATE users SET exp=?, level=?, balance=balance+? WHERE id=?",
        (new_exp, new_lvl, money, user_id),
    )
    if money > 0:
        _add_tx(cur, user_id, money, 'work', 'Заработок на работе')
    db.commit()
    return new_lvl, new_exp


def _add_tx(cur: sqlite3.Cursor, user_id: int, amount: int,
            tx_type: str, description: str) -> None:
    cur.execute(
        "INSERT INTO transactions (user_id, amount, type, timestamp, description) VALUES (?,?,?,?,?)",
        (user_id, amount, tx_type, int(time.time()), description),
    )


def add_transaction(db: sqlite3.Connection, cur: sqlite3.Cursor,
                    user_id: int, amount: int, tx_type: str, description: str) -> None:
    _add_tx(cur, user_id, amount, tx_type, description)
    db.commit()


def add_gang_log(db: sqlite3.Connection, cur: sqlite3.Cursor,
                 gang_id: int, user_id: int, action: str, details: str = "") -> None:
    cur.execute(
        "INSERT INTO gang_logs (gang_id, user_id, action, timestamp, details) VALUES (?,?,?,?,?)",
        (gang_id, user_id, action, int(time.time()), details),
    )
    db.commit()


# ──────────────────────────────────────────────────────────
#  Декораторы
# ──────────────────────────────────────────────────────────

def require_registered(func):
    """Декоратор для обработчиков Message: проверяет регистрацию."""
    @wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        cur: sqlite3.Cursor = kwargs.get('cur') or (args[0] if args else None)
        if cur is None:
            # ищем cur в kwargs под другим именем
            for v in kwargs.values():
                if isinstance(v, sqlite3.Cursor):
                    cur = v
                    break
        if cur and not cur.execute("SELECT 1 FROM users WHERE id=?", (message.from_user.id,)).fetchone():
            await message.answer("❌ Сначала зарегистрируйтесь — отправьте /start")
            return
        return await func(message, *args, **kwargs)
    return wrapper


def require_registered_cb(func):
    """Декоратор для обработчиков CallbackQuery: проверяет регистрацию."""
    @wraps(func)
    async def wrapper(callback: types.CallbackQuery, *args, **kwargs):
        cur: sqlite3.Cursor = kwargs.get('cur') or (args[0] if args else None)
        if cur is None:
            for v in kwargs.values():
                if isinstance(v, sqlite3.Cursor):
                    cur = v
                    break
        if cur and not cur.execute("SELECT 1 FROM users WHERE id=?", (callback.from_user.id,)).fetchone():
            await callback.answer("❌ Сначала зарегистрируйтесь — отправьте /start", show_alert=True)
            return
        return await func(callback, *args, **kwargs)
    return wrapper


def admin_only(func):
    """Декоратор для Message: только для администраторов."""
    from config import ADMIN_IDS
    @wraps(func)
    async def wrapper(message: types.Message, *args, **kwargs):
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("❌ Нет прав доступа!")
            return
        return await func(message, *args, **kwargs)
    return wrapper


def admin_only_cb(func):
    """Декоратор для CallbackQuery: только для администраторов."""
    from config import ADMIN_IDS
    @wraps(func)
    async def wrapper(callback: types.CallbackQuery, *args, **kwargs):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("❌ Нет прав доступа!", show_alert=True)
            return
        return await func(callback, *args, **kwargs)
    return wrapper
