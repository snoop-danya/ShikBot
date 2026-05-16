#!/usr/bin/env python3
# ============================================================
#  main.py — точка входа
# ============================================================

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import API_TOKEN
from database import get_connection, init_db
from utils.middleware import DbMiddleware, AntiFloodMiddleware
import bot_instance

# Импортируем все роутеры
from handlers.registration import router as reg_router
from handlers.profile       import router as profile_router
from handlers.work          import router as work_router
from handlers.mining        import router as mining_router
from handlers.gangs         import router as gangs_router
from handlers.quests        import router as quests_router
from handlers.top           import router as top_router
from handlers.promo         import router as promo_router
from handlers.admin         import router as admin_router
from handlers.settings      import router as settings_router
from handlers.background    import hourly_income_loop, daily_reset_loop, crypto_price_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


async def main() -> None:
    db, cur = get_connection()
    init_db(db, cur)

    log.info("📊 Игроков: %d",    cur.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    log.info("🔫 Банд: %d",       cur.execute("SELECT COUNT(*) FROM gangs").fetchone()[0])
    log.info("🗺  Территорий: %d", cur.execute("SELECT COUNT(*) FROM territories").fetchone()[0])

    bot_instance.bot = Bot(
        token=API_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.update.middleware(DbMiddleware(cur, db))
    dp.update.middleware(AntiFloodMiddleware(msg_rate=5, msg_window=5, cb_rate=3, cb_window=2))

    dp.include_routers(
        reg_router,
        profile_router,
        work_router,
        mining_router,
        gangs_router,
        quests_router,
        top_router,
        promo_router,
        admin_router,
        settings_router,
    )

    asyncio.create_task(hourly_income_loop(db, cur))
    asyncio.create_task(daily_reset_loop(db, cur))
    asyncio.create_task(crypto_price_loop(db, cur))

    log.info("🤖 Бот Shakal Game запускается...")
    try:
        await bot_instance.bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot_instance.bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot_instance.bot.session.close()
        log.info("🛑 Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
