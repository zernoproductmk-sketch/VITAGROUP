# Статус запуска production — 24.09.2026

## Закрыто

- Актуализация/проверка данных в REG.RU успешно завершена.
- Последний CI проекта на ветке main завершен успешно.
- Production-конфигурация приложения, Docker Compose, миграции до `013_qc_inspections.sql`, post-deploy checks и безопасная пилотная загрузка справочников подготовлены.

## Следующий этап

1. Подтвердить наличие production VPS и его публичного IPv4.
2. Настроить A-запись `corpvitagroup.ru` на production IPv4.
3. Дождаться публичного DNS-разрешения домена.
4. Выполнить серверный preflight:
   `sh infra/server-preflight.sh .env`
5. Собрать контейнеры:
   `docker compose build`
6. Запустить PostgreSQL и миграции:
   `docker compose up -d db migrate`
7. После успешных миграций запустить приложение:
   `docker compose up -d`
8. Проверить:
   - `https://corpvitagroup.ru/`
   - `https://corpvitagroup.ru/health`
   - schema version `013_qc_inspections.sql`
   - database status `ok`
9. Создать первого администратора только на сервере.
10. После проверки production выполнить пилотную загрузку справочников:
    линии → сотрудники → номенклатура → тарифы.
11. Перейти к контрольной тестовой смене и пройти lifecycle до `VERIFIED`.

## Важно

Секреты, реальные пароли, API-токены, персональные данные, тарифные ставки и production-выгрузки в GitHub не записываются.
