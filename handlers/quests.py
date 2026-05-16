# ============================================================
#  handlers/quests.py — квесты
# ============================================================

import time
import sqlite3

from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import Quests
from utils.helpers import (
    require_registered, require_registered_cb,
    safe_json_loads, safe_json_dumps,
    add_transaction, fmt, progress_bar,
)

router = Router(name="quests")


def _ensure_reset(cur: sqlite3.Cursor, db: sqlite3.Connection, uid: int) -> tuple[dict, dict]:
    """Сбрасывает квесты если нужно, возвращает (daily, weekly)."""
    row = cur.execute(
        "SELECT daily_quests, weekly_quests, last_daily_reset, last_weekly_reset FROM users WHERE id=?", (uid,)
    ).fetchone()
    now = int(time.time())

    daily  = safe_json_loads(row[0], {})
    weekly = safe_json_loads(row[1], {})
    changed = False

    if now - (row[2] or 0) >= 86_400:
        daily = {}
        cur.execute("UPDATE users SET daily_quests='{}', last_daily_reset=? WHERE id=?", (now, uid))
        changed = True

    if now - (row[3] or 0) >= 604_800:
        weekly = {}
        cur.execute("UPDATE users SET weekly_quests='{}', last_weekly_reset=? WHERE id=?", (now, uid))
        changed = True

    if changed:
        db.commit()

    return daily, weekly


@router.message(F.text == "📜 Квесты")
@require_registered
async def quests_menu(message: types.Message, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid = message.from_user.id
    daily, weekly = _ensure_reset(cur, db, uid)

    text = "📜 <b>СИСТЕМА КВЕСТОВ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "📅 <b>ЕЖЕДНЕВНЫЕ:</b>\n"
    total_avail = 0

    for qid, q in Quests.DAILY_QUESTS.items():
        prog = daily.get(str(qid), 0)
        done = prog >= q['target']
        if done:
            status = "✅"
            total_avail += q['reward']
        else:
            bar    = progress_bar(prog, q['target'])
            pct    = min(100, int((prog / q['target']) * 100)) if q['target'] else 0
            status = f"{bar} {pct}%"
        text += f"{q['emoji']} {status} {q['name']} — {fmt(q['reward'])}₽\n"

    text += "\n📆 <b>ЕЖЕНЕДЕЛЬНЫЕ:</b>\n"
    for qid, q in Quests.WEEKLY_QUESTS.items():
        prog = weekly.get(str(qid), 0)
        done = prog >= q['target']
        if done:
            status = "✅"
            total_avail += q['reward']
        else:
            bar    = progress_bar(prog, q['target'])
            pct    = min(100, int((prog / q['target']) * 100)) if q['target'] else 0
            status = f"{bar} {pct}%"
        text += f"{q['emoji']} {status} {q['name']} — {fmt(q['reward'])}₽\n"

    text += f"\n💰 <b>К получению: {fmt(total_avail)}₽</b>"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Забрать награды", callback_data="claim_quests")],
        [InlineKeyboardButton(text="🔄 Обновить",        callback_data="refresh_quests")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "refresh_quests")
@require_registered_cb
async def refresh_quests(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    await quests_menu(callback.message, cur=cur, db=db)
    await callback.answer("✅ Обновлено")


@router.callback_query(F.data == "claim_quests")
@require_registered_cb
async def claim_quests(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid = callback.from_user.id
    daily, weekly = _ensure_reset(cur, db, uid)

    total   = 0
    claimed = []

    for qid, q in Quests.DAILY_QUESTS.items():
        key = str(qid)
        if daily.get(key, 0) >= q['target']:
            total += q['reward']
            claimed.append(q['name'])
            daily[key] = 0   # сбрасываем прогресс после получения

    for qid, q in Quests.WEEKLY_QUESTS.items():
        key = str(qid)
        if weekly.get(key, 0) >= q['target']:
            total += q['reward']
            claimed.append(q['name'])
            weekly[key] = 0

    if not total:
        await callback.answer("❌ Нет выполненных квестов!", show_alert=True)
        return

    cur.execute(
        "UPDATE users SET balance=balance+?, daily_quests=?, weekly_quests=? WHERE id=?",
        (total, safe_json_dumps(daily), safe_json_dumps(weekly), uid),
    )
    add_transaction(db, cur, uid, total, 'quest_reward', f'Награда за {len(claimed)} квестов')

    quest_list = "\n".join(f"• {q}" for q in claimed[:6])
    if len(claimed) > 6:
        quest_list += f"\n• ещё {len(claimed)-6}..."

    await callback.message.edit_text(
        f"🎉 <b>Получено {fmt(total)}₽</b>\n\n{quest_list}",
        parse_mode="HTML",
    )
    await quests_menu(callback.message, cur=cur, db=db)
