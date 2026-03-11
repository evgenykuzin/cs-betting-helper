# CS Betting Helper

Сервис для мониторинга коэффициентов на матчи CS2, детекции аномалий и поиска арбитражных возможностей.

## 🎯 Возможности

- ✅ **Мониторинг 350+ букмекеров** через OddsPapi API
- ✅ **Детекция аномалий** — резкие движения коэффициентов
- ✅ **Поиск арбитража** — прибыльные спреды между букмекерами
- ✅ **Хранение временных рядов** — TimescaleDB для анализа истории
- 🚧 **Telegram бот** для уведомлений (в разработке)
- 🚧 **ML-модели** для предсказания (в планах)

---

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Установить пакеты
pip install -r requirements.txt
```

### 2. Настройка API ключа

Создайте `.env` файл:

```bash
cp .env.example .env
```

Добавьте ваш OddsPapi API key в `.env`:

```env
ODDSPAPI_API_KEY=your_key_here
```

Получить ключ: https://oddspapi.io (бесплатный tier доступен!)

### 3. Запуск теста интеграции

```bash
python test_integration.py
```

Вывод:
```
✅ Found 15 matches with odds
✅ Found odds from 10 bookmakers
💰 ARBITRAGE FOUND! Profit: 3.82%
```

---

## 🗄️ База данных (опционально)

Для хранения временных рядов коэффициентов:

```bash
# Запустить TimescaleDB + Redis
docker-compose up -d

# Применить схему
docker exec -i cs-betting-timescaledb psql -U cs_user -d cs_betting < db/schema.sql
```

Обновите `.env`:

```env
DATABASE_URL=postgresql://cs_user:cs_password@localhost:5432/cs_betting
REDIS_URL=redis://localhost:6379/0
```

---

## 📂 Структура проекта

```
cs-betting-helper/
├── src/
│   ├── core/
│   │   ├── models.py          # Унифицированные модели (Match, Odds)
│   │   └── interfaces.py      # BaseProvider интерфейс
│   ├── providers/
│   │   └── oddspapi.py        # OddsPapi API интеграция
│   ├── analysis/              # Детекция аномалий, арбитраж
│   └── storage/               # БД, кэш (TODO)
├── db/
│   └── schema.sql             # Схема PostgreSQL + TimescaleDB
├── docker-compose.yml         # TimescaleDB + Redis
├── test_integration.py        # ✅ Работающий тест
└── README.md
```

---

## 🧪 Примеры использования

### Получить матчи CS2 с коэффициентами

```python
from providers.oddspapi import OddspapiProvider
from datetime import datetime, timedelta

async with OddspapiProvider(api_key) as provider:
    matches = await provider.fetch_matches(
        sport="cs2",
        from_date=datetime.now(),
        to_date=datetime.now() + timedelta(days=7),
        has_odds=True
    )
    
    for match in matches:
        print(f"{match.team1.name} vs {match.team2.name}")
        print(f"  Tournament: {match.tournament}")
        print(f"  Start: {match.start_time}")
```

### Сравнить коэффициенты букмекеров

```python
match = await provider.fetch_match_odds(match_id)

for bk_odds in match.bookmaker_odds:
    print(f"{bk_odds.bookmaker}: {bk_odds.odds.team1_win} / {bk_odds.odds.team2_win}")

# Лучшие коэффициенты
best_t1 = match.best_odds_team1
print(f"Best for {match.team1.name}: {best_t1.odds.team1_win} @ {best_t1.bookmaker}")
```

### Найти арбитраж

```python
best_t1 = match.best_odds_team1
best_t2 = match.best_odds_team2

arb_sum = (1 / best_t1.odds.team1_win) + (1 / best_t2.odds.team2_win)

if arb_sum < 1:
    profit = ((1 / arb_sum) - 1) * 100
    print(f"💰 ARBITRAGE! Profit: {profit:.2f}%")
```

---

## 🔧 Разработка

### Добавить нового провайдера (например, парсер 1xBet)

1. Создать `src/providers/parser_1xbet.py`
2. Наследоваться от `BaseProvider`
3. Реализовать методы `fetch_matches()` и `fetch_match_odds()`
4. Возвращать данные в модели `Match`

Пример:

```python
from core.interfaces import BaseProvider
from core.models import Match, Team, BookmakerOdds, Odds

class Parser1xBet(BaseProvider):
    @property
    def name(self) -> str:
        return "parser_1xbet"
    
    async def fetch_matches(self, sport="cs2", **kwargs) -> List[Match]:
        # Парсинг с помощью Playwright/BeautifulSoup
        ...
        return matches
```

---

## 📊 API Endpoints (будущее)

Планируется FastAPI REST API:

```
GET  /api/matches             # Список матчей
GET  /api/matches/{id}/odds   # Коэффициенты по матчу
GET  /api/anomalies           # Обнаруженные аномалии
GET  /api/arbitrage           # Арбитражные возможности
POST /api/subscribe           # Подписка на алерты
```

---

## 🤝 Contribution

1. Fork репозиторий
2. Создать feature branch (`git checkout -b feature/amazing-feature`)
3. Commit изменения (`git commit -m 'Add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Открыть Pull Request

---

## 📝 Лицензия

MIT License

---

## 🙏 Credits

- **OddsPapi** — https://oddspapi.io
- **TimescaleDB** — https://www.timescale.com
- **Rich** — https://rich.readthedocs.io

---

## 📞 Контакты

Telegram: [@your_username]

**Built with ❤️ for CS2 betting enthusiasts**
