# Anime Together

Початковий каркас сайту для синхронного перегляду аніме. Каталог автоматично
підтягується з AniList, а сам відеофайл залишається на пристрої користувача.
Сервер передає лише стан плеєра, чат і відбиток файла для перевірки версії.

## Що вже працює

- пошук і популярний каталог через AniList GraphQL;
- кешування аніме та автоматичне створення серій у PostgreSQL;
- створення кімнати з коротким інвайт-кодом;
- локальний MP4/WebM без завантаження відео на сервер;
- перевірка, що учасники вибрали однаковий файл;
- синхронні `play`, `pause`, перемотування та швидкість;
- чат кімнати через WebSocket;
- швидкий знімок стану кімнати в Redis;
- початкова Alembic-міграція.

> Браузерна підтримка MKV залежить від кодеків і зазвичай гірша. Для першої
> версії найнадійніше використовувати MP4 (H.264/AAC) або WebM.

## Швидкий запуск через Docker

```bash
cp .env.example .env
docker compose up --build
```

Після запуску:

- сайт: <http://localhost:8000>
- API-документація: <http://localhost:8000/docs>

## Деплой на Render

У корені вже є `render.yaml`. Він створює і з'єднує три ресурси:

- Python Web Service;
- Render Postgres;
- Render Key Value.

Після пушу репозиторію відкрий Render → Blueprints → New Blueprint Instance,
вибери репозиторій і натисни Deploy Blueprint. Міграція БД запускається перед
стартом Uvicorn у `startCommand`, тому окрема ручна команда для першого деплою
не потрібна.

## Запуск без контейнера для застосунку

PostgreSQL і Redis усе одно можна підняти через Docker:

```bash
docker compose up -d db redis
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

У Windows активація середовища:

```powershell
.venv\Scripts\activate
```

Каталог наповнюється ліниво під час пошуку. Щоб одразу закешувати 250
популярних тайтлів:

```bash
python -m scripts.seed_catalog --pages 5 --per-page 50
```

## Основні файли

```text
app/main.py          запуск FastAPI та сторінки
app/config.py        змінні середовища
app/database.py      async SQLAlchemy
app/models.py        усі таблиці БД
app/schemas.py       валідація API
app/crud.py          робота з каталогом і кімнатами
app/anilist.py       клієнт AniList GraphQL
app/realtime.py      WebSocket-з'єднання та Redis-стан
app/routers/         API каталогу, кімнат і синхронізації
templates/           головна сторінка та кімната
static/              один CSS і один JS для поточного інтерфейсу
alembic/             міграції PostgreSQL
scripts/seed_catalog.py  початкове наповнення каталогу
```

## WebSocket-протокол кімнати

Підключення:

```text
ws://localhost:8000/ws/rooms/AB12CD34?name=Alex&user_id=<optional-uuid>
```

Керування плеєром:

```json
{
  "type": "pause",
  "current_time": 483.2,
  "playback_rate": 1
}
```

Допустимі події: `play`, `pause`, `seek`, `rate`, `source`, `chat`.

## Наступний етап

1. Нормальна реєстрація та авторизація замість гостьових користувачів.
2. Сторінка конкретного аніме і вибір номера серії.
3. Перепідключення WebSocket після втрати мережі.
4. Redis Pub/Sub для кількох процесів API.
5. Офіційні YouTube-вбудовування як друге джерело.
6. Списки користувача, історія і продовження перегляду.
