# 🐺 Shakal Game Bot — v2.0

## Структура проекта

```
shakal_bot/
├── main.py                  # Точка входа, сборка бота
├── config.py                # Все настройки и игровые константы
├── database.py              # Инициализация БД и миграции
├── requirements.txt
│
├── utils/
│   ├── helpers.py           # Утилиты, декораторы, игровая логика
│   ├── keyboards.py         # Клавиатуры
│   └── middleware.py        # DbMiddleware + AntiFloodMiddleware
│
└── handlers/
    ├── registration.py      # /start, регистрация
    ├── profile.py           # Профиль, статистика
    ├── work.py              # Работа + казино
    ├── mining.py            # Майнинг, видеокарты, BTC
    ├── gangs.py             # Банды, склад, участники
    ├── quests.py            # Квесты
    ├── top.py               # Топы и рейтинги
    ├── promo.py             # Промокоды + рефералы
    ├── admin.py             # Админ-панель (/admin)
    ├── settings.py          # Настройки пользователя
    └── background.py        # Фоновые задачи (hourly, daily, crypto)
```

## Быстрый старт

1. **Установите зависимости:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Настройте `config.py`:**
   ```python
   API_TOKEN = 'ВАШ_ТОКЕН'        # токен от @BotFather
   ADMIN_IDS = {123456789}         # ваш Telegram ID (числовой)
   ADMIN_USERNAME = "@ваш_ник"
   ```

3. **Запустите:**
   ```bash
   python main.py
   ```

## Что улучшено (v2.0)

### 🐛 Исправленные баги
- **Race condition при регистрации** — двойная проверка перед INSERT
- **Неатомарные транзакции** — деньги и запись в `transactions` теперь в одной транзакции
- **Кривые индексы callback.data** — `kick_member_`, `accept_request_` и т.д. теперь парсятся безопасно
- **Ошибка логики daily_bonus** — бонус выдавался при каждом /start, теперь только раз в 24ч
- **Проверка баланса перед покупкой карты** — была уязвимость к переходу в отрицательный баланс
- **Флуд в фоновой задаче** — добавлен `db.rollback()` при ошибке
- **admin проверялся по username** (ненадёжно) — теперь по `user_id` из `ADMIN_IDS`

### 🛡 Защита
- **AntiFloodMiddleware** — лимит 5 сообщений/5сек, 3 callback/2сек
- **Декоратор `@admin_only` / `@admin_only_cb`** — проверка по `ADMIN_IDS`
- **Валидация ника** — regex + проверка длины
- **Безопасный парсинг callback.data** — try/except при split/int
- **WAL mode + foreign keys** в SQLite

### ⚡️ Производительность
- **Индексы** на часто используемые колонки (balance, level, mining_power, referrer_id и т.д.)
- **PRAGMA journal_mode=WAL** — меньше блокировок при параллельном доступе

### 🗂 Архитектура
- Разбито на 10 роутеров + utils
- Единая точка конфига (`config.py`)
- Единый `fmt()` для форматирования чисел
- Декораторы авторизации вынесены в `utils/helpers.py`
