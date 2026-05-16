# ============================================================
#  handlers/gangs.py — банды
# ============================================================

import time
import sqlite3

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import GangRanks, GANG_CREATION_COST, GANG_DEFAULT_MAX_MEMBERS
from utils.helpers import (
    require_registered, require_registered_cb,
    add_gang_log, add_transaction, fmt, ts_to_str,
)

router = Router(name="gangs")


class GangStates(StatesGroup):
    waiting_for_name        = State()
    waiting_for_description = State()


# ──────────────────────────────────────────────────────────
#  Вспомогательные
# ──────────────────────────────────────────────────────────

def _get_user_gang(cur: sqlite3.Cursor, uid: int) -> tuple | None:
    """Возвращает (gang_id, gang_rank) или None."""
    row = cur.execute("SELECT gang_id, gang_rank FROM users WHERE id=?", (uid,)).fetchone()
    if row and row[0] and row[0] > 0:
        return row
    return None


def _gang_main_kb(uid: int, cur: sqlite3.Cursor, gang_id: int, rank: int) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="👥 Участники",    callback_data="gang_members"),
         InlineKeyboardButton(text="📦 Склад",        callback_data="gang_storage")],
        [InlineKeyboardButton(text="🗺 Территории",   callback_data="gang_territories"),
         InlineKeyboardButton(text="📜 Лог",          callback_data="gang_log")],
    ]
    if rank >= 3:
        kb.append([InlineKeyboardButton(text="📑 Заявки",     callback_data="view_requests"),
                   InlineKeyboardButton(text="🚪 Выгнать",    callback_data="kick_member_start")])
    if rank == 4:
        kb.append([InlineKeyboardButton(text="🎖 Ранги",      callback_data="change_ranks_start"),
                   InlineKeyboardButton(text="💣 Распустить", callback_data="disband_gang_confirm")])
    kb.append([InlineKeyboardButton(text="🚪 Покинуть банду", callback_data="leave_gang_confirm")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ──────────────────────────────────────────────────────────
#  Главное меню банд
# ──────────────────────────────────────────────────────────

@router.message(F.text == "🔫 Банды")
@require_registered
async def gangs_menu(message: types.Message, cur: sqlite3.Cursor, **_):
    uid   = message.from_user.id
    ugang = _get_user_gang(cur, uid)

    if not ugang:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"➕ Создать банду ({fmt(GANG_CREATION_COST)}₽)", callback_data="create_gang_start")],
            [InlineKeyboardButton(text="🔍 Список банд",  callback_data="list_gangs")],
        ])
        await message.answer(
            "🔫 <b>БАНДЫ</b>\n\nТы не состоишь в банде.\n"
            "Создай свою или вступи в существующую!",
            reply_markup=kb, parse_mode="HTML",
        )
        return

    gang_id, rank = ugang
    g = cur.execute("SELECT name, balance, members_count, level, description FROM gangs WHERE gang_id=?", (gang_id,)).fetchone()
    rank_name = GangRanks.RANKS.get(rank, {}).get("name", "—")
    text = (
        f"🔫 <b>БАНДА: {g[0]}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Уровень: {g[3]} | 👥 Участников: {g[2]}\n"
        f"💰 Общак: {fmt(g[1])}₽\n"
        f"🎖 Твой ранг: {rank_name}\n\n"
        f"<i>{g[4] or 'Без описания'}</i>"
    )
    await message.answer(text, reply_markup=_gang_main_kb(uid, cur, gang_id, rank), parse_mode="HTML")


# ──────────────────────────────────────────────────────────
#  Создание банды
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "create_gang_start")
@require_registered_cb
async def create_gang_start(callback: types.CallbackQuery, state: FSMContext, cur: sqlite3.Cursor, **_):
    if _get_user_gang(cur, callback.from_user.id):
        await callback.answer("❌ Вы уже в банде!", show_alert=True)
        return
    balance = cur.execute("SELECT balance FROM users WHERE id=?", (callback.from_user.id,)).fetchone()[0]
    if balance < GANG_CREATION_COST:
        await callback.answer(f"❌ Нужно {fmt(GANG_CREATION_COST)}₽", show_alert=True)
        return
    await callback.message.answer(
        f"🔫 <b>Создание банды</b>\n\nВведите название банды (3–20 символов):",
        parse_mode="HTML",
    )
    await state.set_state(GangStates.waiting_for_name)


@router.message(GangStates.waiting_for_name)
async def gang_name_input(message: types.Message, state: FSMContext, cur: sqlite3.Cursor, **_):
    name = message.text.strip() if message.text else ""
    if not 3 <= len(name) <= 20:
        await message.answer("❌ Название должно быть от 3 до 20 символов!")
        return
    if cur.execute("SELECT 1 FROM gangs WHERE name=?", (name,)).fetchone():
        await message.answer("❌ Банда с таким названием уже существует!")
        return
    await state.update_data(gang_name=name)
    await message.answer("📝 Введите описание банды (до 100 символов, или «-» пропустить):")
    await state.set_state(GangStates.waiting_for_description)


@router.message(GangStates.waiting_for_description)
async def gang_desc_input(message: types.Message, state: FSMContext,
                          cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    desc    = message.text.strip() if message.text else ""
    desc    = "" if desc == "-" else desc[:100]
    data    = await state.get_data()
    name    = data.get("gang_name", "Банда")
    uid     = message.from_user.id
    now     = int(time.time())

    # Ещё раз проверяем баланс (защита от гонки)
    balance = cur.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    if balance < GANG_CREATION_COST:
        await message.answer("❌ Недостаточно средств!")
        await state.clear()
        return

    cur.execute(
        "INSERT INTO gangs (name, owner_id, description, created_at, max_members) VALUES (?,?,?,?,?)",
        (name, uid, desc, now, GANG_DEFAULT_MAX_MEMBERS),
    )
    gang_id = cur.lastrowid
    cur.execute("UPDATE users SET gang_id=?, gang_rank=4, balance=balance-? WHERE id=?",
                (gang_id, GANG_CREATION_COST, uid))
    add_transaction(db, cur, uid, -GANG_CREATION_COST, 'gang_creation', f'Создание банды {name}')
    add_gang_log(db, cur, gang_id, uid, "Создание банды", f"Основана банда «{name}»")
    await state.clear()

    await message.answer(
        f"🎉 <b>Банда «{name}» создана!</b>\n\n"
        f"💰 Списано: {fmt(GANG_CREATION_COST)}₽\n"
        f"🎖 Вы стали Лидером!",
        parse_mode="HTML",
    )


# ──────────────────────────────────────────────────────────
#  Список банд
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "list_gangs")
@require_registered_cb
async def list_gangs(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    gangs = cur.execute(
        "SELECT gang_id, name, members_count, level, balance FROM gangs ORDER BY level DESC, balance DESC LIMIT 15"
    ).fetchall()

    if not gangs:
        text = "🔫 <b>БАНДЫ</b>\n\nПока нет ни одной банды. Создай первую!"
    else:
        text = "🔫 <b>ВСЕ БАНДЫ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, g in enumerate(gangs, 1):
            text += f"{i}. <b>{g[1]}</b> · {g[2]} чел. · LVL {g[3]} · {fmt(g[4])}₽\n"

    uid   = callback.from_user.id
    ugang = _get_user_gang(cur, uid)

    kb_rows = []
    if not ugang:
        for g in gangs:
            kb_rows.append([InlineKeyboardButton(
                text=f"📩 Вступить: {g[1][:15]}",
                callback_data=f"join_gang_{g[0]}",
            )])

    kb_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="gangs_back")])
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")


@router.callback_query(F.data == "gangs_back")
@require_registered_cb
async def gangs_back(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    await gangs_menu(callback.message, cur=cur)


@router.callback_query(F.data.startswith("join_gang_"))
@require_registered_cb
async def join_gang(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid = callback.from_user.id
    if _get_user_gang(cur, uid):
        await callback.answer("❌ Вы уже в банде!", show_alert=True)
        return

    try:
        gang_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    gang = cur.execute("SELECT name, members_count, max_members FROM gangs WHERE gang_id=?", (gang_id,)).fetchone()
    if not gang:
        await callback.answer("❌ Банда не найдена!", show_alert=True)
        return
    if gang[1] >= gang[2]:
        await callback.answer("❌ Банда переполнена!", show_alert=True)
        return

    # Удаляем старую заявку, создаём новую
    cur.execute("DELETE FROM gang_requests WHERE user_id=?", (uid,))
    cur.execute("INSERT INTO gang_requests (user_id, gang_id, timestamp) VALUES (?,?,?)",
                (uid, gang_id, int(time.time())))
    db.commit()
    await callback.answer(f"✅ Заявка в банду «{gang[0]}» отправлена!", show_alert=True)


# ──────────────────────────────────────────────────────────
#  Склад (общак)
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "gang_storage")
@require_registered_cb
async def gang_storage(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid   = callback.from_user.id
    ugang = _get_user_gang(cur, uid)
    if not ugang:
        await callback.answer("❌ Вы не в банде!", show_alert=True)
        return
    gang_id, rank = ugang

    g       = cur.execute("SELECT name, balance, materials FROM gangs WHERE gang_id=?", (gang_id,)).fetchone()
    u_bal   = cur.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]

    text = (
        f"📦 <b>СКЛАД БАНДЫ «{g[0]}»</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Общак: {fmt(g[1])}₽\n"
        f"🧱 Материалы: {g[2]} шт.\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Ваш баланс: {fmt(u_bal)}₽"
    )
    amounts = [10_000, 50_000, 100_000, 500_000]
    dep_row = [InlineKeyboardButton(text=f"↑ {fmt(a)}₽", callback_data=f"st_dep_{a}") for a in amounts]
    kb_rows = [dep_row[:2], dep_row[2:]]
    if rank >= 3:
        wd_row  = [InlineKeyboardButton(text=f"↓ {fmt(a)}₽", callback_data=f"st_wd_{a}") for a in amounts]
        kb_rows += [wd_row[:2], wd_row[2:]]
    kb_rows.append([InlineKeyboardButton(text="🔙 К банде", callback_data="back_to_gang_main")])
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")


@router.callback_query(F.data.startswith("st_"))
@require_registered_cb
async def storage_action(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid = callback.from_user.id
    ugang = _get_user_gang(cur, uid)
    if not ugang:
        await callback.answer("❌ Вы не в банде!", show_alert=True)
        return
    gang_id, rank = ugang

    parts = callback.data.split("_")
    action = parts[1]   # dep | wd
    try:
        amount = int(parts[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    if action == "dep":
        u_bal = cur.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
        if u_bal < amount:
            await callback.answer(f"❌ У вас только {fmt(u_bal)}₽", show_alert=True)
            return
        cur.execute("UPDATE users SET balance=balance-? WHERE id=?", (amount, uid))
        cur.execute("UPDATE gangs SET balance=balance+? WHERE gang_id=?", (amount, gang_id))
        add_transaction(db, cur, uid, -amount, 'gang_deposit', 'Вклад в общак')
        add_gang_log(db, cur, gang_id, uid, "Вклад в общак", f"{fmt(amount)}₽")
        await callback.answer(f"✅ Внесено {fmt(amount)}₽", show_alert=True)

    elif action == "wd":
        if rank < 3:
            await callback.answer("❌ Только зам/лидер могут снимать!", show_alert=True)
            return
        g_bal = cur.execute("SELECT balance FROM gangs WHERE gang_id=?", (gang_id,)).fetchone()[0]
        if g_bal < amount:
            await callback.answer(f"❌ В общаке только {fmt(g_bal)}₽", show_alert=True)
            return
        cur.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, uid))
        cur.execute("UPDATE gangs SET balance=balance-? WHERE gang_id=?", (amount, gang_id))
        add_transaction(db, cur, uid, amount, 'gang_withdraw', 'Снятие с общака')
        add_gang_log(db, cur, gang_id, uid, "Снятие с общака", f"{fmt(amount)}₽")
        await callback.answer(f"✅ Снято {fmt(amount)}₽", show_alert=True)

    db.commit()
    await gang_storage(callback, cur=cur, db=db)


# ──────────────────────────────────────────────────────────
#  Участники
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "gang_members")
@require_registered_cb
async def gang_members(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid   = callback.from_user.id
    ugang = _get_user_gang(cur, uid)
    if not ugang:
        await callback.answer("❌ Вы не в банде!", show_alert=True)
        return
    gang_id, _ = ugang

    members = cur.execute("""
        SELECT id, nickname, gang_rank, level FROM users
        WHERE gang_id=? ORDER BY gang_rank DESC, level DESC LIMIT 30
    """, (gang_id,)).fetchall()

    text = f"👥 <b>УЧАСТНИКИ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for m in members:
        rank_name = GangRanks.RANKS.get(m[2] or 0, {}).get("name", "—")
        text += f"• {m[1]} · {rank_name} · LVL {m[3]}\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К банде", callback_data="back_to_gang_main")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


# ──────────────────────────────────────────────────────────
#  Заявки
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "view_requests")
@require_registered_cb
async def view_requests(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid   = callback.from_user.id
    ugang = _get_user_gang(cur, uid)
    if not ugang or ugang[1] < 3:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    gang_id = ugang[0]

    reqs = cur.execute("""
        SELECT gr.user_id, u.nickname, u.level, u.balance, gr.timestamp
        FROM gang_requests gr JOIN users u ON gr.user_id=u.id
        WHERE gr.gang_id=? ORDER BY gr.timestamp DESC LIMIT 10
    """, (gang_id,)).fetchall()

    if not reqs:
        text = "📑 <b>ЗАЯВОК НЕТ</b>"
    else:
        text = "📑 <b>ЗАЯВКИ НА ВСТУПЛЕНИЕ</b>\n\n"
        for r in reqs:
            text += f"• {r[1]} · LVL {r[2]} · {fmt(r[3])}₽ · {ts_to_str(r[4], '%H:%M')}\n"

    kb_rows = [[
        InlineKeyboardButton(text=f"✅ {r[1][:10]}", callback_data=f"accept_request_{r[0]}"),
        InlineKeyboardButton(text=f"❌ {r[1][:10]}", callback_data=f"reject_request_{r[0]}"),
    ] for r in reqs]
    kb_rows.append([InlineKeyboardButton(text="🔙 К банде", callback_data="back_to_gang_main")])
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")


@router.callback_query(F.data.startswith("accept_request_"))
@require_registered_cb
async def accept_request(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **kwargs):
    uid = callback.from_user.id
    ugang = _get_user_gang(cur, uid)
    if not ugang or ugang[1] < 3:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    gang_id = ugang[0]

    try:
        target_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    req = cur.execute("SELECT 1 FROM gang_requests WHERE user_id=? AND gang_id=?", (target_id, gang_id)).fetchone()
    if not req:
        await callback.answer("❌ Заявка не найдена!", show_alert=True)
        return

    # Проверяем что игрок ещё не в банде
    if _get_user_gang(cur, target_id):
        cur.execute("DELETE FROM gang_requests WHERE user_id=?", (target_id,))
        db.commit()
        await callback.answer("❌ Игрок уже вступил в другую банду!", show_alert=True)
        return

    g_info = cur.execute("SELECT members_count, max_members FROM gangs WHERE gang_id=?", (gang_id,)).fetchone()
    if g_info[0] >= g_info[1]:
        await callback.answer("❌ Достигнут лимит участников!", show_alert=True)
        return

    nick = cur.execute("SELECT nickname FROM users WHERE id=?", (target_id,)).fetchone()[0]
    cur.execute("UPDATE users SET gang_id=?, gang_rank=1 WHERE id=?", (gang_id, target_id))
    cur.execute("UPDATE gangs SET members_count=members_count+1 WHERE gang_id=?", (gang_id,))
    cur.execute("DELETE FROM gang_requests WHERE user_id=?", (target_id,))
    add_gang_log(db, cur, gang_id, uid, "Принятие в банду", f"Принят {nick}")

    # Уведомляем принятого
    import bot_instance as _bi
    try:
        await _bi.bot.send_message(target_id,
            "🎉 <b>Вас приняли в банду!</b>\n🎖 Ваш ранг: Рекрут 🟢",
            parse_mode="HTML")
    except Exception:
        pass

    await callback.answer(f"✅ {nick} принят!", show_alert=True)
    await view_requests(callback, cur=cur, db=db)


@router.callback_query(F.data.startswith("reject_request_"))
@require_registered_cb
async def reject_request(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid   = callback.from_user.id
    ugang = _get_user_gang(cur, uid)
    if not ugang or ugang[1] < 3:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return

    try:
        target_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    cur.execute("DELETE FROM gang_requests WHERE user_id=?", (target_id,))
    db.commit()

    import bot_instance as _bi
    try:
        await _bi.bot.send_message(target_id,
            "❌ <b>Заявка отклонена.</b>\nПопробуйте другую банду!",
            parse_mode="HTML")
    except Exception:
        pass

    await callback.answer("✅ Заявка отклонена", show_alert=True)
    await view_requests(callback, cur=cur, db=db)


# ──────────────────────────────────────────────────────────
#  Исключение / выход
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "kick_member_start")
@require_registered_cb
async def kick_member_start(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid   = callback.from_user.id
    ugang = _get_user_gang(cur, uid)
    if not ugang or ugang[1] < 3:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    gang_id, rank = ugang

    members = cur.execute("""
        SELECT id, nickname, gang_rank FROM users
        WHERE gang_id=? AND id!=? AND gang_rank < ?
        ORDER BY gang_rank, nickname LIMIT 20
    """, (gang_id, uid, rank if rank < 4 else 4)).fetchall()

    if not members:
        await callback.answer("❌ Нет участников для исключения!", show_alert=True)
        return

    text = "🚪 <b>Выберите участника для исключения:</b>\n\n"
    kb_rows = []
    for m in members:
        rn = GangRanks.RANKS.get(m[2] or 0, {}).get("name", "—")
        text += f"• {m[1]} — {rn}\n"
        kb_rows.append([InlineKeyboardButton(
            text=f"🚪 {m[1][:15]}", callback_data=f"kick_member_{m[0]}"
        )])
    kb_rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="gang_members")])
    try:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")


@router.callback_query(F.data.startswith("kick_member_"))
@require_registered_cb
async def kick_member(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid   = callback.from_user.id
    ugang = _get_user_gang(cur, uid)
    if not ugang or ugang[1] < 3:
        await callback.answer("❌ Нет прав!", show_alert=True)
        return
    gang_id, rank = ugang

    try:
        target_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return

    target = cur.execute("SELECT gang_id, gang_rank, nickname FROM users WHERE id=?", (target_id,)).fetchone()
    if not target or target[0] != gang_id:
        await callback.answer("❌ Пользователь не в вашей банде!", show_alert=True)
        return
    if target[1] >= rank:
        await callback.answer("❌ Нельзя исключить равного или старшего!", show_alert=True)
        return

    cur.execute("UPDATE users SET gang_id=0, gang_rank=0 WHERE id=?", (target_id,))
    cur.execute("UPDATE gangs SET members_count=members_count-1 WHERE gang_id=?", (gang_id,))
    add_gang_log(db, cur, gang_id, uid, "Исключение", f"Исключён {target[2]}")

    import bot_instance as _bi
    try:
        await _bi.bot.send_message(target_id,
            f"🚪 <b>Вы исключены из банды!</b>",
            parse_mode="HTML")
    except Exception:
        pass

    await callback.answer(f"✅ {target[2]} исключён!", show_alert=True)
    await gang_members(callback, cur=cur, db=db)


@router.callback_query(F.data == "leave_gang_confirm")
@require_registered_cb
async def leave_gang_confirm(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    ugang = _get_user_gang(cur, callback.from_user.id)
    if not ugang:
        await callback.answer("❌ Вы не в банде!", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, покинуть", callback_data="leave_gang_do"),
         InlineKeyboardButton(text="❌ Отмена",        callback_data="back_to_gang_main")],
    ])
    try:
        await callback.message.edit_text(
            "⚠️ <b>Вы уверены, что хотите покинуть банду?</b>",
            reply_markup=kb, parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            "⚠️ <b>Вы уверены, что хотите покинуть банду?</b>",
            reply_markup=kb, parse_mode="HTML",
        )


@router.callback_query(F.data == "leave_gang_do")
@require_registered_cb
async def leave_gang_do(callback: types.CallbackQuery, cur: sqlite3.Cursor, db: sqlite3.Connection, **_):
    uid   = callback.from_user.id
    ugang = _get_user_gang(cur, uid)
    if not ugang:
        await callback.answer("❌ Вы не в банде!", show_alert=True)
        return
    gang_id, rank = ugang

    if rank == 4:
        members_count = cur.execute("SELECT members_count FROM gangs WHERE gang_id=?", (gang_id,)).fetchone()[0]
        if members_count > 1:
            await callback.answer("❌ Лидер не может покинуть банду пока есть участники.\nПередайте лидерство или распустите банду.", show_alert=True)
            return

    nick = cur.execute("SELECT nickname FROM users WHERE id=?", (uid,)).fetchone()[0]
    cur.execute("UPDATE users SET gang_id=0, gang_rank=0 WHERE id=?", (uid,))
    cur.execute("UPDATE gangs SET members_count=members_count-1 WHERE gang_id=?", (gang_id,))
    add_gang_log(db, cur, gang_id, uid, "Выход из банды", f"{nick} покинул банду")
    await callback.answer("✅ Вы покинули банду.", show_alert=True)
    await callback.message.answer("Главное меню:", reply_markup=__import__('utils.keyboards', fromlist=['main_menu']).main_menu())


@router.callback_query(F.data == "back_to_gang_main")
@require_registered_cb
async def back_to_gang_main(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    await gangs_menu(callback.message, cur=cur)


# ──────────────────────────────────────────────────────────
#  Лог банды
# ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "gang_log")
@require_registered_cb
async def gang_log(callback: types.CallbackQuery, cur: sqlite3.Cursor, **_):
    uid   = callback.from_user.id
    ugang = _get_user_gang(cur, uid)
    if not ugang:
        await callback.answer("❌ Вы не в банде!", show_alert=True)
        return
    gang_id = ugang[0]

    logs = cur.execute("""
        SELECT gl.action, gl.details, gl.timestamp, u.nickname
        FROM gang_logs gl LEFT JOIN users u ON gl.user_id=u.id
        WHERE gl.gang_id=? ORDER BY gl.timestamp DESC LIMIT 20
    """, (gang_id,)).fetchall()

    text = "📜 <b>ЛОГ БАНДЫ</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for l in logs:
        dt = ts_to_str(l[2], '%d.%m %H:%M')
        text += f"<i>{dt}</i> · <b>{l[0]}</b>\n{l[3] or '?'}: {l[1] or ''}\n\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К банде", callback_data="back_to_gang_main")]
    ])
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
