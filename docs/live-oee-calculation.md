# Реальный расчет OEE из PostgreSQL

Главный дашборд больше не зависит от backend mock-данных. Endpoint `/api/v1/dashboard/summary` рассчитывает показатели из рабочих таблиц.

## Источники расчета

- план и норматив: `production_runs`;
- выпуск: `production_output_events`;
- брак оператора и ОТК: `defect_events`;
- простои: `downtime_events`;
- приемка склада: `warehouse_receipts`;
- факт 1С/ERP: `erp_production_facts`.

## Availability

Для каждого запуска определяется расчетный интервал внутри смены.

`Run Time = Planned Time - counted unplanned downtime`

В Availability попадают только неплановые простои, у которых причина влияет на доступность. Если причина еще не классифицирована, простой считается влияющим на Availability.

## Performance

`Performance = Output / (Ideal Rate × Run Time)`

Норматив берется из snapshot `production_runs.ideal_rate_per_hour`.

Если хотя бы у одного учитываемого запуска отсутствует норматив, агрегированный Performance и OEE возвращаются как `null`, а frontend показывает предупреждение. Система не подставляет выдуманную норму.

Performance выше 100% не обрезается.

## Quality

На текущем этапе подтвержденным браком для OEE считается:

`reported_by = QC AND is_confirmed = true`.

`Good Count = Output - Confirmed QC Defect`

При этом брак оператора показывается отдельно для сверки.

## Онлайн-смена

Если смена еще идет, расчетный конец интервала — текущее время. Для прошлой смены используется конец смены / фактический конец запуска.

Форма выпуска Coverse теперь обновляет у `production_runs`:

- `actual_start_at`;
- `actual_end_at`;
- статус RUNNING / COMPLETED.

## Сводный OEE

Агрегирование выполняется по физическим величинам, а не средним процентов:

- Availability = суммарное Run Time / суммарное Planned Time;
- Performance = общий выпуск / сумму теоретического выпуска по каждому запуску;
- Quality = общий Good Count / общий Output;
- OEE = Availability × Performance × Quality.

## API

- `GET /api/v1/dashboard/summary`
- `GET /api/v1/oee/runs`
- `GET /api/v1/equipment`
- `GET /api/v1/downtime`
- `GET /api/v1/reconciliation`

Параметры:

- `business_date=YYYY-MM-DD`;
- `shift_code=DAY|NIGHT`.

Если параметры не переданы, backend сам определяет текущую бизнес-смену по часовому поясу `Europe/Moscow`.

## Защита от дублей

Уникальность внешних фактов теперь действует только для строк, у которых `source_record_id IS NOT NULL`. Это позволяет создавать несколько ручных/system-событий без ложного конфликта по NULL.
