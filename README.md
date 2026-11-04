# Discord-бот-помощник

Универсальный бот для Discord на **Python (discord.py)**: информация о сервере и участниках, модерация, опросы, напоминания, мини-развлечения.

Хостинг: **AWS Free Tier** — EC2 `t2.micro` бесплатно 12 месяцев (750 часов/мес, бот 24/7 влезает: ~720 часов в месяце).

## Команды

| Категория | Команды |
|---|---|
| Общие | `/ping` `/help` `/serverinfo` `/userinfo` `/avatar` |
| Модерация | `/kick` `/ban` `/unban` `/timeout` `/untimeout` `/clear` |
| Утилиты | `/say` `/poll` `/remind` `/8ball` `/coinflip` |

## Структура

```
discord-bot/
├── bot.py              # точка входа
├── utils.py            # парсер времени (10m, 1h30m, 2d)
├── cogs/
│   ├── general.py      # общие команды
│   ├── moderation.py   # модерация
│   └── utility.py      # утилиты и развлечения
├── requirements.txt
├── .env.example        # шаблон настроек
└── deploy/
    └── setup-ec2.sh    # автоматическая настройка сервера
```

---

## Шаг 1. Создание бота в Discord

1. Открой <https://discord.com/developers/applications> → **New Application** (задай имя).
2. Вкладка **Bot** → **Reset Token** → **Copy** (это токен; не публикуй его).
3. Там же включи **Server Members Intent** (раздел Privileged Gateway Intents) — без него бот не запустится.
4. Вкладка **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Kick Members`, `Ban Members`, `Moderate Members`, `Manage Messages`
   - Скопируй **URL**, открой в браузере и пригласи бота на сервер.

## Шаг 2. Локальный запуск (проверка)

```powershell
cd "C:\Users\ST2\Documents\Default Project\discord-bot"
py -3 -m venv venv
venv\Scripts\pip install -r requirements.txt
copy .env.example .env
notepad .env        # вставь токен, при желании — ID сервера
venv\Scripts\python bot.py
```

`GUILD_ID` (ID сервера: ПКМ по серверу при включённом Developer Mode → Copy Server ID) — необязателен, но с ним команды появляются сразу, без него ждать до ~1 часа.

## Шаг 3. Регистрация в AWS

1. <https://aws.amazon.com/free/> → **Create an AWS Account** (нужны e-mail, карта, телефон).
2. После входа в консоль: **Services → EC2 → Launch Instance**:
   - **Name**: `discord-bot`
   - **AMI**: Ubuntu Server 24.04 LTS (Free tier eligible)
   - **Instance type**: `t2.micro` (Free tier eligible)
   - **Key pair**: Create new pair → имя `discord-bot-key` → **Download .pem** (положи в `C:\Users\ST2\Downloads`)
   - **Network settings → Edit → Security groups**: создать новую, оставить только **SSH (TCP22)**, Source: **My IP**
   - Остальное по умолчанию → **Launch instance**
3. Регион — по умолчанию N. Virginia (`us-east-1`), там free tier действует.

## Шаг 4. Загрузка кода на сервер

Public DNS сервера смотри в консоли EC2 (например `ec2-54-160-11-22.compute.amazonaws.com`), подключение:

```powershell
ssh -i "C:\Users\ST2\Downloads\discord-bot-key.pem" ubuntu@<Public-DNS>
```

Если Windows ругается на права ключа (`UNPROTECTED PRIVATE KEY FILE`):

```powershell
icacls "C:\Users\ST2\Downloads\discord-bot-key.pem" /inheritance:r /grant "R:$env:USERNAME"
```

**Вариант А — scp** (в PowerShell, с твоей машины):

```powershell
scp -i "C:\Users\ST2\Downloads\discord-bot-key.pem" -r "C:\Users\ST2\Documents\Default Project\discord-bot" ubuntu@<Public-DNS>:~/
```

**Вариант B — GitHub** (загой репозиторий и на сервере):

```bash
git clone <url-репозитория> ~/discord-bot
```

## Шаг 5. Установка и запуск

На сервере (по SSH):

```bash
bash ~/discord-bot/deploy/setup-ec2.sh
```

Скрипт сам поставит Python, зависимости и systemd-сервис. Дальше:

```bash
nano ~/discord-bot/.env      # вставь DISCORD_TOKEN (и GUILD_ID)
sudo systemctl enable --now discord-bot
sudo systemctl status discord-bot    # должно быть active (running)
sudo journalctl -u discord-bot -f    # живые логи (Ctrl+C — выйти)
```

В логах должно появиться `Бот запущен: <имя>` и `Команды привязаны...`.

## Управление

```bash
sudo systemctl restart discord-bot   # перезапуск
sudo systemctl stop discord-bot      # стоп
```

## Обновление бота

С локальной машины (PowerShell) закинь изменённый код и перезапусти:

```powershell
scp -i "C:\Users\ST2\Downloads\discord-bot-key.pem" -r "C:\Users\ST2\Documents\Default Project\discord-bot\*" ubuntu@<Public-DNS>:~/discord-bot/
ssh -i "C:\Users\ST2\Downloads\discord-bot-key.pem" ubuntu@<Public-DNS> "sudo systemctl restart discord-bot"
```

## Важно

- Файл `.env` с токеном **никогда** не публикуй и не коммить (в `.gitignore` уже есть).
- Утечка токена → Reset Token в Developer Portal и обнови `.env` на сервере.
- Free tier: 750 часов/мес `t2.micro` в течение **12 месяцев**. Один работающий бот — ~720 часов, влезает. Через год — либо платить (~$0.01/ч), либо переехать на Oracle Cloud Always Free.
- Когда бот не нужен подолгу — `sudo systemctl stop discord-bot` и останови инстанс в консоли EC2, чтобы не жечь часы.
