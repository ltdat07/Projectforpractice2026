# Network Core Management Backend

Backend демонстрационной веб-панели для управления сетевыми профилями,
конфигурациями и Xray Core.

## Реализовано

- FastAPI и SQLite;
- CRUD сетевых профилей;
- хранение полного JSON-конфига Xray внутри профиля;
- проверка конфига командой Xray `run -test -c`;
- запуск Xray командой `run -c`;
- остановка и перезапуск процесса;
- получение runtime-статуса и PID;
- чтение последних строк лога;
- журнал действий;
- режим `demo` для frontend-разработки без `xray.exe`;
- CORS для frontend на портах 3000 и 5173.

## Режимы

### Demo

Используется по умолчанию. API и интерфейс можно разрабатывать без Xray.
Активация меняет статус, но внешний процесс не запускается.

```cmd
set NETWORK_CORE_MODE=demo
fastapi dev app/main.py
```

### Реальный Xray

1. Скачайте официальный Windows-архив Xray Core.
2. Распакуйте `xray.exe` и сопутствующие файлы, например в:

```text
C:\Tools\Xray\
```

3. В той же консоли задайте переменные и запустите backend:

```cmd
set NETWORK_CORE_MODE=xray
set XRAY_EXECUTABLE=C:\Tools\Xray\xray.exe
fastapi dev app/main.py
```

Переменные `set` действуют только в текущем окне cmd.

## Запуск проекта

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
fastapi dev app/main.py
```

- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## API

### Профили

| Метод | URL | Назначение |
|---|---|---|
| GET | `/api/profiles` | Список профилей |
| GET | `/api/profiles/{id}` | Один профиль |
| POST | `/api/profiles` | Создать профиль |
| PATCH | `/api/profiles/{id}` | Изменить профиль |
| DELETE | `/api/profiles/{id}` | Удалить профиль |

### Управление ядром

| Метод | URL | Назначение |
|---|---|---|
| POST | `/api/profiles/{id}/validate` | Проверить конфиг |
| POST | `/api/profiles/{id}/activate` | Запустить Xray |
| POST | `/api/profiles/{id}/deactivate` | Остановить Xray |
| POST | `/api/profiles/{id}/restart` | Перезапустить Xray |
| GET | `/api/profiles/{id}/runtime` | Реальный статус и PID |
| GET | `/api/profiles/{id}/logs?lines=200` | Последние строки лога |
| GET | `/api/actions` | Журнал действий |

## Быстрая проверка

1. Создайте профиль содержимым файла
   `examples/xray_direct_socks_profile.json` через Swagger.
2. Вызовите `/validate`.
3. В реальном режиме вызовите `/activate`.
4. Проверьте `/runtime` и `/logs`.
5. Вызовите `/deactivate`.
6. Откройте `/api/actions`.

## Тесты

```cmd
python -m pytest -v
```

Автоматические тесты используют demo-режим и не требуют `xray.exe`.
Реальную проверку официального бинарного файла нужно выполнить вручную один раз.
