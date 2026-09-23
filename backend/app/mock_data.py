DASHBOARD_SUMMARY = {
    "status": "ONLINE",
    "shift": {
        "business_date": "2026-09-23",
        "type": "DAY",
        "label": "ДЕНЬ",
        "time": "09:00–21:00",
    },
    "kpi": {
        "oee": 76.4,
        "availability": 88.2,
        "performance": 91.5,
        "quality": 94.7,
    },
    "production": {
        "plan": 82000,
        "operator_output": 61450,
        "good_product": 59870,
        "operator_defect": 1580,
        "qc_defect": 1490,
        "warehouse_received": 59320,
        "erp_fact": 58900,
    },
    "equipment": [
        {
            "code": "LINE-01",
            "name": "Пакетоделательная линия №1",
            "state": "RUNNING",
            "oee": 82.1,
            "product": "Пакет бумажный 320×200",
            "output": 18400,
            "downtime_minutes": 22,
        },
        {
            "code": "LINE-02",
            "name": "Пакетоделательная линия №2",
            "state": "DOWNTIME",
            "oee": 68.7,
            "product": "Пакет бумажный 260×150",
            "output": 13950,
            "downtime_minutes": 57,
            "downtime_reason": "Ожидание материала",
        },
        {
            "code": "LINE-03",
            "name": "Пакетоделательная линия №3",
            "state": "RUNNING",
            "oee": 78.4,
            "product": "Пакет бумажный 400×240",
            "output": 16600,
            "downtime_minutes": 31,
        },
        {
            "code": "LINE-04",
            "name": "Печатная машина №1",
            "state": "RUNNING",
            "oee": 74.9,
            "product": "Печать / заказ ERP-260923-18",
            "output": 12500,
            "downtime_minutes": 44,
        },
    ],
}

DOWNTIME = [
    {"equipment": "LINE-02", "start": "12:34", "end": None, "minutes": 57, "reason": "Ожидание материала", "planned": False},
    {"equipment": "LINE-03", "start": "10:11", "end": "10:29", "minutes": 18, "reason": "Переналадка", "planned": True},
    {"equipment": "LINE-01", "start": "09:42", "end": "09:58", "minutes": 16, "reason": "Регулировка оборудования", "planned": False},
]

RECONCILIATION = [
    {"product": "Арт. 34001", "operator": 12400, "qc_good": 12280, "warehouse": 12240, "erp": 12240},
    {"product": "Арт. 37008", "operator": 8200, "qc_good": 8170, "warehouse": 8150, "erp": 8100},
    {"product": "Арт. 41012", "operator": 15600, "qc_good": 15340, "warehouse": 15180, "erp": 15000},
]

PAYROLL = [
    {"employee": "Иванов И.И.", "shifts": 14, "approved_quantity": 183400, "amount": 184250},
    {"employee": "Петров П.П.", "shifts": 13, "approved_quantity": 171200, "amount": 176840},
    {"employee": "Сидоров А.А.", "shifts": 15, "approved_quantity": 194600, "amount": 191320},
]
