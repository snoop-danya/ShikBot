# ============================================================
#  utils/middleware.py — middleware (БД + защита от флуда)
# ============================================================

import time
import logging
from collections import defaultdict
from typing import Callable, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

log = logging.getLogger(__name__)


class DbMiddleware(BaseMiddleware):
    """Прокидывает cursor и connection в каждый хендлер."""

    def __init__(self, cursor, connection):
        self.cursor     = cursor
        self.connection = connection

    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        data['cur'] = self.cursor
        data['db']  = self.connection
        return await handler(event, data)


class AntiFloodMiddleware(BaseMiddleware):
    """
    Простой rate-limiter:
      - Message:       не чаще `msg_rate` сообщений за `msg_window` секунд
      - CallbackQuery: не чаще `cb_rate` нажатий за `cb_window` секунд
    """

    def __init__(
        self,
        msg_rate: int   = 5,
        msg_window: int = 5,
        cb_rate: int    = 3,
        cb_window: int  = 2,
    ):
        self.msg_rate   = msg_rate
        self.msg_window = msg_window
        self.cb_rate    = cb_rate
        self.cb_window  = cb_window

        # user_id → [timestamp, ...]
        self._msg_hist: dict[int, list[float]] = defaultdict(list)
        self._cb_hist:  dict[int, list[float]] = defaultdict(list)

    def _check(self, hist: dict, user_id: int, rate: int, window: int) -> bool:
        now = time.monotonic()
        timestamps = hist[user_id]
        # удаляем старые записи
        hist[user_id] = [t for t in timestamps if now - t < window]
        if len(hist[user_id]) >= rate:
            return False          # заблокирован
        hist[user_id].append(now)
        return True

    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        user_id: int | None = None

        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            if user_id and not self._check(self._msg_hist, user_id, self.msg_rate, self.msg_window):
                log.warning("Flood (msg) user_id=%s", user_id)
                try:
                    await event.answer("🚫 Вы слишком часто отправляете сообщения. Подождите немного.")
                except Exception:
                    pass
                return

        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            if user_id and not self._check(self._cb_hist, user_id, self.cb_rate, self.cb_window):
                log.warning("Flood (cb) user_id=%s", user_id)
                try:
                    await event.answer("🚫 Не так быстро!", show_alert=False)
                except Exception:
                    pass
                return

        return await handler(event, data)
