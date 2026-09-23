# Авторизация и роли

## Вход

Рабочий сайт использует email + пароль.

Пароли:

- никогда не хранятся в открытом виде;
- хэшируются Argon2 через `pwdlib`;
- минимальная длина — 12 символов.

После успешного входа backend выдает JWT access token. В production секрет JWT хранится только в `.env` сервера.

Срок сессии по умолчанию — 8 часов.

После 5 неудачных попыток учетная запись временно блокируется на 15 минут.

Все попытки входа пишутся в `auth_login_events`.

## Роли

- OPERATOR — оператор;
- ACCOUNTANT_PRODUCTION — учетчик производства;
- WAREHOUSE — кладовщик;
- QC — ОТК;
- SHIFT_MASTER — сменный мастер;
- PRODUCTION_MANAGER — руководитель производства;
- ECONOMIST — экономист;
- MANAGEMENT — руководство;
- ADMIN — администратор.

Один пользователь может иметь несколько ролей.

## Первый администратор

Пароль администратора не хранится в GitHub.

После первого развертывания:

```bash
docker compose exec backend python -m app.create_admin --email admin@company.ru
```

Команда запросит пароль интерактивно. Альтернативно на время команды можно передать `VITAGROUP_ADMIN_PASSWORD` через окружение.

Первый вход требует смены пароля.

## API

- `POST /api/v1/auth/login`;
- `GET /api/v1/auth/me`;
- `POST /api/v1/auth/change-password`.

Администратор:

- `GET /api/v1/admin/users`;
- `POST /api/v1/admin/users`;
- `PUT /api/v1/admin/users/{id}/roles`;
- `PUT /api/v1/admin/users/{id}/active`.

## Правило доступа

Frontend скрывает недоступные разделы для удобства пользователя, но это не является защитой само по себе. Backend независимо проверяет JWT и роли для закрытых API.
