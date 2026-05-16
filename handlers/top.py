# ============================================================
#  handlers/top.py — топы и рейтинги
# ============================================================

import time
import sqlite3

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import TOP_REWARD_COOLDOWN
from utils.helpers import require_registered, require_registered_cb, fmt, medal, add_transaction

router = Router(name="top")


def _build_top_text(cur: sqlite3.Cursor) -> str:
    rich    = cur.execute("SELECT nickname, balance FROM users WHERE nickname IS NOT NULL ORDER BY balance DESC LIMIT 5").fetchall()
    levels  = cur.execute("SELECT nickname, level, exp FROM users WHERE nickname IS NOT NULL ORDER BY level DESC, exp DESC LIMIT 5").fetchall()
    miners  = cur.execute("SELECT nickname, mining_power FROM users WHERE nickname IS NOT NULL AND mining_power>0 ORDER BY mining_power DESC LIMIT 5").fetchall()
    gang_t  = cur.execute("SELECT name, members_count, balance FROM gangs ORDER BY balance DESC LIMIT 5").fetchall()

    text = "🏆 <b>ДОСКА ПОЧЁТА</b>\n\n"

    text += "💰 <b>ТОП БОГАЧЕЙ:</b>\n"
    for i, u in enumerate(rich, 1):
        text += f"{medal(i)} {u[0]} — {fmt(u[1])}₽\n"

    text += "\n📊 <b>ТОП ПО УРОВНЮ:</b>\n"
    for i, u in enumerate(levels, 1):
        text += f"{medal(i)} {u[0]} — {u[1]} LVL\n"

    text += "\n⚡️ <b>ТОП МАЙНЕРОВ:</b>\n"
    for i, u in enumerate(miners, 1):
        text += f"{medal(i)} {u[0]} — {u[1]} MH/s\n"

    text += "\n🔫 <b>ТОП БАНД:</b>\n"
    for i, g in enumerate(gang_t, 1):
        text += f"{medal(i)} {g[0]} — {g[1]} чел. · {fmt(g[2])}₽\n"

    text += "\n🎁 <i>Топ-3 в категории получает бонус раз в 24ч</i>"
    return text


@router.message(F.text == "🏆 ТОП")
@require_registered
async def top_menu(message: types.Message, cur: sqlite3.Cursor, **_):
    text = _build_top_text(cur)
    kb   = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Бонус богача",  callback_data="claim_rich_reward"),
         InlineKeyboardButton(text="📊 Бонус уровня",  callback_data="claim_level_reward")],
        [InlineKeyboardButton(text="⚡️ Бонус майнера", callback_data="claim_mining_reward")],
        [InlineKeyboardButton(text="🔄 Обновить",       callback_data="refresh_top")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "refresh_top")
@require_registered_cb
async def refresh_top(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    text = _build_top_text(cur)
    kb   = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Бонус богача",  callback_data="claim_rich_reward"),
         InlineKeyboardButton(text="📊 Бонус уровня",  callback_data="claim_level_reward")],
        [InlineKeyboardButton(text="⚡️ Бонус майнера", callback_data="claim_mining_reward")],
        [InlineKeyboardButton(text="🔄 Обновить",       callback_data="refresh_top")],
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("✅ Обновлено")


def _claim_top_reward(cur: sqlite3.Cursor, db: sqlite3.Connection,
                      uid: int, query: str, rewards: dict, category: str):
    """Общая логика получения топ-бонуса. Возвращает (reward, place) или (None, None)."""
    top3 = [r[0] for r in cur.execute(query).fetchall()]
    if uid not in top3:
        return None, None

    last_r = cur.execute("SELECT last_top_reward FROM users WHERE id=?", (uid,)).fetchone()[0] or 0
    if int(time.time()) - last_r < TOP_REWARD_COOLDOWN:
        return -1, None   # cooldown

    place  = top3.index(uid) + 1
    reward = rewards.get(place, 0)

    cur.execute("UPDATE users SET balance=balance+?, last_top_reward=? WHERE id=?",
                (reward, int(time.time()), uid))
    add_transaction(db, cur, uid, reward, 'top_reward', f'Бонус Топ-{place} ({category})')
    return reward, place


@router.callback_query(F.data == "claim_rich_reward")
@require_registered_cb
async def claim_rich(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    reward, place = _claim_top_reward(
        cur, db, callback.from_user.id,
        "SELECT id FROM users ORDER BY balance DESC LIMIT 3",
        {1: 1_000_000, 2: 500_000, 3: 250_000},
        "Богачи",
    )
    if reward is None:
        await callback.answer("❌ Вы не в Топ-3 богачей!", show_alert=True)
    elif reward == -1:
        await callback.answer("⏳ Можно раз в 24 часа!", show_alert=True)
    else:
        await callback.answer(f"🎉 +{fmt(reward)}₽ за {place} место!", show_alert=True)


@router.callback_query(F.data == "claim_level_reward")
@require_registered_cb
async def claim_level(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    reward, place = _claim_top_reward(
        cur, db, callback.from_user.id,
        "SELECT id FROM users ORDER BY level DESC, exp DESC LIMIT 3",
        {1: 500_000, 2: 250_000, 3: 100_000},
        "Уровень",
    )
    if reward is None:
        await callback.answer("❌ Вы не в Топ-3 по уровню!", show_alert=True)
    elif reward == -1:
        await callback.answer("⏳ Можно раз в 24 часа!", show_alert=True)
    else:
        await callback.answer(f"🎉 +{fmt(reward)}₽ за {place} место!", show_alert=True)


@router.callback_query(F.data == "claim_mining_reward")
@require_registered_cb
async def claim_mining(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    reward, place = _claim_top_reward(
        cur, db, callback.from_user.id,
        "SELECT id FROM users WHERE mining_power>0 ORDER BY mining_power DESC LIMIT 3",
        {1: 500_000, 2: 250_000, 3: 100_000},
        "Майнинг",
    )
    if reward is None:
        await callback.answer("❌ Вы не в Топ-3 майнеров!", show_alert=True)
    elif reward == -1:
        await callback.answer("⏳ Можно раз в 24 часа!", show_alert=True)
    else:
        await callback.answer(f"🎉 +{fmt(reward)}₽ за {place} место!", show_alert=True)
