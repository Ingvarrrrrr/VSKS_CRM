#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import urllib.request
import json

API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwNTE5NDgzNi04MWU5LTQ2NWItODNkMy05NDhhM2U5NDI2OTciLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMWRhOWM4MmYtZmNjNy00ZGY1LWJhZGUtODZjMDZjNmQyNDUzIiwiaWF0IjoxNzcyNDkzNjkxfQ.VLT4MK1wpap4G1wBBwWsaiDd1IP-Dqo9USUdP-FX5xk"
BASE = "http://localhost:5678/api/v1"

def create_workflow(workflow):
    data = json.dumps(workflow, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/workflows",
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-N8N-API-KEY": API_KEY,
        },
        method="POST"
    )
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read().decode("utf-8"))
        print(f"✅ Создан: {result['name']} (id={result['id']})")
        return result

# Workflow 1: Ежедневная проверка бюджета
wf1 = {
    "name": "CRM: Ежедневная проверка бюджета",
    "nodes": [
        {
            "id": "trigger-daily",
            "name": "Каждый день 9:00",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [200, 300],
            "parameters": {
                "rule": {
                    "interval": [{"field": "cronExpression", "expression": "0 9 * * 1-5"}]
                }
            }
        },
        {
            "id": "get-subsidies",
            "name": "Субсидии из API",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [420, 200],
            "parameters": {
                "method": "GET",
                "url": "http://backend:8000/api/subsidies/",
                "options": {}
            }
        },
        {
            "id": "get-purchases",
            "name": "Закупки из API",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [420, 400],
            "parameters": {
                "method": "GET",
                "url": "http://backend:8000/api/purchases/",
                "options": {}
            }
        },
        {
            "id": "code-analyze",
            "name": "Анализ бюджета",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [660, 300],
            "parameters": {
                "jsCode": """
const subsidies = $('Субсидии из API').all().map(i => i.json);
const purchases = $('Закупки из API').all().map(i => i.json);

const LIMIT = 26128070;
const totalPlanned = purchases.reduce((s, p) => s + parseFloat(p.planned_total_price || 0), 0);
const totalConfirmed = purchases.filter(p => p.confirmed).reduce((s, p) => s + parseFloat(p.final_total_amount || 0), 0);
const pct = (totalConfirmed / LIMIT * 100).toFixed(1);

const byStatus = {};
purchases.forEach(p => { byStatus[p.status] = (byStatus[p.status] || 0) + 1; });

const statusLine = Object.entries(byStatus)
  .map(([s, c]) => `  - ${s}: ${c} шт.`)
  .join('\\n');

const report = [
  '📊 ЕЖЕДНЕВНЫЙ ОТЧЁТ CRM VSKS',
  `📅 Дата: ${new Date().toLocaleDateString('ru-RU')}`,
  '',
  `💰 Лимит субсидии: ${LIMIT.toLocaleString('ru-RU')} ₽`,
  `📋 Запланировано: ${totalPlanned.toLocaleString('ru-RU')} ₽`,
  `✅ Подтверждено: ${totalConfirmed.toLocaleString('ru-RU')} ₽`,
  `📊 Освоение: ${pct}% от лимита`,
  `📦 Всего закупок: ${purchases.length}`,
  `🏢 Активных субсидий: ${subsidies.length}`,
  '',
  '📈 По статусам:',
  statusLine,
].join('\\n');

const alert = parseFloat(pct) >= 80
  ? `⚠️ ПРЕВЫШЕНО 80% ЛИМИТА! Использовано ${pct}%`
  : null;

return [{ json: { report, alert, pct: parseFloat(pct), totalConfirmed, totalPlanned, LIMIT, isAlert: !!alert } }];
"""
            }
        },
        {
            "id": "if-alert",
            "name": "Превышен порог?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [880, 300],
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [{"id": "cond1", "leftValue": "={{ $json.isAlert }}", "rightValue": True, "operator": {"type": "boolean", "operation": "true"}}],
                    "combinator": "and"
                }
            }
        },
        {
            "id": "set-result",
            "name": "Лог отчёта",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [1100, 400],
            "parameters": {
                "assignments": {
                    "assignments": [
                        {"id": "1", "name": "status", "value": "OK", "type": "string"},
                        {"id": "2", "name": "report", "value": "={{ $json.report }}", "type": "string"},
                        {"id": "3", "name": "pct", "value": "={{ $json.pct }}", "type": "number"}
                    ]
                }
            }
        },
        {
            "id": "set-alert",
            "name": "Лог предупреждения",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [1100, 200],
            "parameters": {
                "assignments": {
                    "assignments": [
                        {"id": "1", "name": "status", "value": "ALERT", "type": "string"},
                        {"id": "2", "name": "report", "value": "={{ $json.report }}", "type": "string"},
                        {"id": "3", "name": "alert", "value": "={{ $json.alert }}", "type": "string"}
                    ]
                }
            }
        }
    ],
    "connections": {
        "Каждый день 9:00": {"main": [[
            {"node": "Субсидии из API", "type": "main", "index": 0},
            {"node": "Закупки из API", "type": "main", "index": 0}
        ]]},
        "Субсидии из API": {"main": [[{"node": "Анализ бюджета", "type": "main", "index": 0}]]},
        "Закупки из API": {"main": [[{"node": "Анализ бюджета", "type": "main", "index": 0}]]},
        "Анализ бюджета": {"main": [[{"node": "Превышен порог?", "type": "main", "index": 0}]]},
        "Превышен порог?": {
            "main": [
                [{"node": "Лог предупреждения", "type": "main", "index": 0}],
                [{"node": "Лог отчёта", "type": "main", "index": 0}]
            ]
        }
    },
    "settings": {"executionOrder": "v1"}
}

# Workflow 2: Webhook - уведомление о новой закупке
wf2 = {
    "name": "CRM: Webhook - новая закупка",
    "nodes": [
        {
            "id": "webhook-in",
            "name": "Webhook входящий",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [200, 300],
            "parameters": {
                "path": "crm-new-purchase",
                "httpMethod": "POST",
                "responseMode": "responseNode"
            },
            "webhookId": "crm-new-purchase"
        },
        {
            "id": "code-format",
            "name": "Форматировать данные",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [420, 300],
            "parameters": {
                "jsCode": """
const body = $input.first().json.body || $input.first().json;
const p = body;

const statusMap = {
  planned: 'Планируется',
  confirmed: 'Подтверждён',
  contracted: 'Подписан',
  delivered: 'Поставлено',
  paid: 'Оплачено'
};

const message = [
  '🛍️ НОВАЯ ЗАКУПКА В CRM',
  `📋 Номер: ${p.order_number || 'N/A'}`,
  `📦 Наименование: ${p.item_name || 'N/A'}`,
  `🏢 Подрядчик: ${p.contractor_name || 'N/A'}`,
  `💰 Сумма: ${parseFloat(p.planned_total_price || 0).toLocaleString('ru-RU')} ₽`,
  `📊 Статус: ${statusMap[p.status] || p.status}`,
].join('\\n');

return [{ json: { message, purchase: p } }];
"""
            }
        },
        {
            "id": "respond",
            "name": "Ответ 200",
            "type": "n8n-nodes-base.respondToWebhook",
            "typeVersion": 1.1,
            "position": [640, 300],
            "parameters": {
                "respondWith": "json",
                "responseBody": "={ \"ok\": true, \"message\": $json.message }"
            }
        }
    ],
    "connections": {
        "Webhook входящий": {"main": [[{"node": "Форматировать данные", "type": "main", "index": 0}]]},
        "Форматировать данные": {"main": [[{"node": "Ответ 200", "type": "main", "index": 0}]]}
    },
    "settings": {"executionOrder": "v1"}
}

# Workflow 3: Еженедельный Excel-отчёт
wf3 = {
    "name": "CRM: Еженедельный Excel-отчёт",
    "nodes": [
        {
            "id": "trigger-weekly",
            "name": "Каждый понедельник 8:00",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [200, 300],
            "parameters": {
                "rule": {
                    "interval": [{"field": "cronExpression", "expression": "0 8 * * 1"}]
                }
            }
        },
        {
            "id": "get-excel",
            "name": "Скачать Excel из CRM",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [420, 300],
            "parameters": {
                "method": "GET",
                "url": "http://backend:8000/api/purchases/export/excel",
                "options": {"response": {"response": {"responseFormat": "file"}}},
                "headers": {"parameters": [{"name": "Authorization", "value": "Bearer ADMIN_TOKEN"}]}
            }
        },
        {
            "id": "set-info",
            "name": "Информация об отчёте",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [640, 300],
            "parameters": {
                "assignments": {
                    "assignments": [
                        {"id": "1", "name": "message", "value": "Еженедельный отчёт CRM VSKS сформирован", "type": "string"},
                        {"id": "2", "name": "date", "value": "={{ new Date().toLocaleDateString('ru-RU') }}", "type": "string"},
                        {"id": "3", "name": "week", "value": "={{ 'Неделя ' + new Date().toLocaleDateString('ru-RU', {month:'long', day:'numeric'}) }}", "type": "string"}
                    ]
                }
            }
        }
    ],
    "connections": {
        "Каждый понедельник 8:00": {"main": [[{"node": "Скачать Excel из CRM", "type": "main", "index": 0}]]},
        "Скачать Excel из CRM": {"main": [[{"node": "Информация об отчёте", "type": "main", "index": 0}]]}
    },
    "settings": {"executionOrder": "v1"}
}

print("Создаю workflows в n8n...\n")
create_workflow(wf1)
create_workflow(wf2)
create_workflow(wf3)
print("\nГотово! Откройте http://localhost:5678 чтобы увидеть workflows.")
