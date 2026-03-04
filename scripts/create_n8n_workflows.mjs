// @ts-check
const API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwNTE5NDgzNi04MWU5LTQ2NWItODNkMy05NDhhM2U5NDI2OTciLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiMWRhOWM4MmYtZmNjNy00ZGY1LWJhZGUtODZjMDZjNmQyNDUzIiwiaWF0IjoxNzcyNDkzNjkxfQ.VLT4MK1wpap4G1wBBwWsaiDd1IP-Dqo9USUdP-FX5xk";
const BASE = "http://localhost:5678/api/v1";

async function createWorkflow(wf) {
  const res = await fetch(`${BASE}/workflows`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-N8N-API-KEY": API_KEY },
    body: JSON.stringify(wf),
  });
  const data = await res.json();
  if (data.id) {
    console.log(`✅ Создан: ${data.name} (id=${data.id})`);
  } else {
    console.log(`❌ Ошибка:`, JSON.stringify(data));
  }
  return data;
}

// Workflow 1: Ежедневная проверка бюджета
const wf1 = {
  name: "CRM: Ежедневная проверка бюджета",
  nodes: [
    {
      id: "trigger-daily", name: "Каждый день 9:00",
      type: "n8n-nodes-base.scheduleTrigger", typeVersion: 1.2,
      position: [200, 300],
      parameters: { rule: { interval: [{ field: "cronExpression", expression: "0 9 * * 1-5" }] } }
    },
    {
      id: "get-subsidies", name: "Субсидии из API",
      type: "n8n-nodes-base.httpRequest", typeVersion: 4.2,
      position: [420, 200],
      parameters: { method: "GET", url: "http://backend:8000/api/subsidies/", options: {} }
    },
    {
      id: "get-purchases", name: "Закупки из API",
      type: "n8n-nodes-base.httpRequest", typeVersion: 4.2,
      position: [420, 400],
      parameters: { method: "GET", url: "http://backend:8000/api/purchases/", options: {} }
    },
    {
      id: "code-analyze", name: "Анализ бюджета",
      type: "n8n-nodes-base.code", typeVersion: 2,
      position: [660, 300],
      parameters: {
        jsCode: `
const subsidies = $('Субсидии из API').all().map(i => i.json);
const purchases = $('Закупки из API').all().map(i => i.json);
const LIMIT = 26128070;
const totalPlanned = purchases.reduce((s, p) => s + parseFloat(p.planned_total_price || 0), 0);
const totalConfirmed = purchases.filter(p => p.confirmed).reduce((s, p) => s + parseFloat(p.final_total_amount || 0), 0);
const pct = (totalConfirmed / LIMIT * 100).toFixed(1);
const byStatus = {};
purchases.forEach(p => { byStatus[p.status] = (byStatus[p.status] || 0) + 1; });
const statusLine = Object.entries(byStatus).map(([s, c]) => \`  - \${s}: \${c} шт.\`).join('\\n');
const report = [
  '📊 ЕЖЕДНЕВНЫЙ ОТЧЁТ CRM VSKS',
  \`📅 Дата: \${new Date().toLocaleDateString('ru-RU')}\`,
  '',
  \`💰 Лимит субсидии: \${LIMIT.toLocaleString('ru-RU')} ₽\`,
  \`📋 Запланировано: \${totalPlanned.toLocaleString('ru-RU')} ₽\`,
  \`✅ Подтверждено: \${totalConfirmed.toLocaleString('ru-RU')} ₽\`,
  \`📈 Освоение: \${pct}% от лимита\`,
  \`📦 Всего закупок: \${purchases.length}\`,
  \`🏢 Активных субсидий: \${subsidies.length}\`,
  '',
  '📊 По статусам:',
  statusLine,
].join('\\n');
const isAlert = parseFloat(pct) >= 80;
const alert = isAlert ? \`⚠️ ПРЕВЫШЕНО 80%! Использовано \${pct}%\` : null;
return [{ json: { report, alert, pct: parseFloat(pct), totalConfirmed, totalPlanned, LIMIT, isAlert } }];
`
      }
    },
    {
      id: "if-alert", name: "Превышен порог?",
      type: "n8n-nodes-base.if", typeVersion: 2,
      position: [880, 300],
      parameters: {
        conditions: {
          options: { caseSensitive: true, leftValue: "", typeValidation: "strict" },
          conditions: [{ id: "c1", leftValue: "={{ $json.isAlert }}", rightValue: true, operator: { type: "boolean", operation: "true" } }],
          combinator: "and"
        }
      }
    },
    {
      id: "set-alert", name: "⚠️ Лог ПРЕДУПРЕЖДЕНИЕ",
      type: "n8n-nodes-base.set", typeVersion: 3.4,
      position: [1100, 200],
      parameters: {
        assignments: { assignments: [
          { id: "1", name: "status", value: "ALERT", type: "string" },
          { id: "2", name: "report", value: "={{ $json.report }}", type: "string" },
          { id: "3", name: "alert", value: "={{ $json.alert }}", type: "string" }
        ]}
      }
    },
    {
      id: "set-ok", name: "✅ Лог OK",
      type: "n8n-nodes-base.set", typeVersion: 3.4,
      position: [1100, 400],
      parameters: {
        assignments: { assignments: [
          { id: "1", name: "status", value: "OK", type: "string" },
          { id: "2", name: "report", value: "={{ $json.report }}", type: "string" },
          { id: "3", name: "pct", value: "={{ $json.pct }}", type: "number" }
        ]}
      }
    }
  ],
  connections: {
    "Каждый день 9:00": { main: [[{ node: "Субсидии из API", type: "main", index: 0 }, { node: "Закупки из API", type: "main", index: 0 }]] },
    "Субсидии из API": { main: [[{ node: "Анализ бюджета", type: "main", index: 0 }]] },
    "Закупки из API": { main: [[{ node: "Анализ бюджета", type: "main", index: 0 }]] },
    "Анализ бюджета": { main: [[{ node: "Превышен порог?", type: "main", index: 0 }]] },
    "Превышен порог?": { main: [
      [{ node: "⚠️ Лог ПРЕДУПРЕЖДЕНИЕ", type: "main", index: 0 }],
      [{ node: "✅ Лог OK", type: "main", index: 0 }]
    ]}
  },
  settings: { executionOrder: "v1" }
};

// Workflow 2: Webhook для уведомлений CRM
const wf2 = {
  name: "CRM: Webhook уведомления о закупках",
  nodes: [
    {
      id: "wh-in", name: "Webhook входящий",
      type: "n8n-nodes-base.webhook", typeVersion: 2,
      position: [200, 300],
      parameters: { path: "crm-purchase-event", httpMethod: "POST", responseMode: "responseNode" },
      webhookId: "crm-purchase-event"
    },
    {
      id: "code-fmt", name: "Форматировать событие",
      type: "n8n-nodes-base.code", typeVersion: 2,
      position: [440, 300],
      parameters: {
        jsCode: `
const body = $input.first().json.body || $input.first().json;
const statusMap = { planned:'Планируется', confirmed:'Подтверждён', contracted:'Подписан', delivered:'Поставлено', paid:'Оплачено' };
const message = [
  '🛍️ СОБЫТИЕ ЗАКУПКИ CRM',
  \`📋 Номер: \${body.order_number || 'N/A'}\`,
  \`📦 Наименование: \${body.item_name || 'N/A'}\`,
  \`🏢 Подрядчик: \${body.contractor_name || 'N/A'}\`,
  \`💰 Сумма: \${parseFloat(body.planned_total_price || 0).toLocaleString('ru-RU')} ₽\`,
  \`📊 Статус: \${statusMap[body.status] || body.status}\`,
].join('\\n');
return [{ json: { message, event: body } }];
`
      }
    },
    {
      id: "respond", name: "Ответ 200 OK",
      type: "n8n-nodes-base.respondToWebhook", typeVersion: 1.1,
      position: [680, 300],
      parameters: { respondWith: "json", responseBody: `={ "ok": true }` }
    }
  ],
  connections: {
    "Webhook входящий": { main: [[{ node: "Форматировать событие", type: "main", index: 0 }]] },
    "Форматировать событие": { main: [[{ node: "Ответ 200 OK", type: "main", index: 0 }]] }
  },
  settings: { executionOrder: "v1" }
};

// Workflow 3: Еженедельный отчёт
const wf3 = {
  name: "CRM: Еженедельный сводный отчёт",
  nodes: [
    {
      id: "trigger-w", name: "Каждый понедельник 8:00",
      type: "n8n-nodes-base.scheduleTrigger", typeVersion: 1.2,
      position: [200, 300],
      parameters: { rule: { interval: [{ field: "cronExpression", expression: "0 8 * * 1" }] } }
    },
    {
      id: "get-all", name: "Все данные CRM",
      type: "n8n-nodes-base.httpRequest", typeVersion: 4.2,
      position: [420, 300],
      parameters: { method: "GET", url: "http://backend:8000/api/purchases/", options: {} }
    },
    {
      id: "code-summary", name: "Сводная статистика",
      type: "n8n-nodes-base.code", typeVersion: 2,
      position: [640, 300],
      parameters: {
        jsCode: `
const purchases = $input.all().map(i => i.json);
const LIMIT = 26128070;
const total = purchases.reduce((s, p) => s + parseFloat(p.planned_total_price || 0), 0);
const confirmed = purchases.filter(p => p.confirmed).reduce((s, p) => s + parseFloat(p.final_total_amount || 0), 0);
const pct = (confirmed / LIMIT * 100).toFixed(1);
const week = new Date().toLocaleDateString('ru-RU', { day:'numeric', month:'long', year:'numeric' });
const contractors = [...new Set(purchases.map(p => p.contractor_id).filter(Boolean))].length;

const report = [
  '📊 ЕЖЕНЕДЕЛЬНЫЙ ОТЧЁТ CRM VSKS',
  \`📅 \${week}\`,
  '═════════════════════════',
  \`📦 Всего закупок: \${purchases.length}\`,
  \`🏢 Задействовано подрядчиков: \${contractors}\`,
  \`💰 Лимит субсидии: \${LIMIT.toLocaleString('ru-RU')} ₽\`,
  \`📋 Запланировано: \${total.toLocaleString('ru-RU')} ₽\`,
  \`✅ Подтверждено: \${confirmed.toLocaleString('ru-RU')} ₽\`,
  \`📈 Освоение: \${pct}% от лимита\`,
  \`💵 Остаток лимита: \${(LIMIT - confirmed).toLocaleString('ru-RU')} ₽\`,
].join('\\n');

return [{ json: { report, week, total, confirmed, pct: parseFloat(pct), purchases: purchases.length, contractors } }];
`
      }
    },
    {
      id: "set-final", name: "Результат отчёта",
      type: "n8n-nodes-base.set", typeVersion: 3.4,
      position: [860, 300],
      parameters: {
        assignments: { assignments: [
          { id: "1", name: "report", value: "={{ $json.report }}", type: "string" },
          { id: "2", name: "week", value: "={{ $json.week }}", type: "string" },
          { id: "3", name: "pct_used", value: "={{ $json.pct }}", type: "number" }
        ]}
      }
    }
  ],
  connections: {
    "Каждый понедельник 8:00": { main: [[{ node: "Все данные CRM", type: "main", index: 0 }]] },
    "Все данные CRM": { main: [[{ node: "Сводная статистика", type: "main", index: 0 }]] },
    "Сводная статистика": { main: [[{ node: "Результат отчёта", type: "main", index: 0 }]] }
  },
  settings: { executionOrder: "v1" }
};

console.log("Создаю workflows в n8n...\n");
await createWorkflow(wf1);
await createWorkflow(wf2);
await createWorkflow(wf3);
console.log("\n✅ Готово! Откройте http://localhost:5678");
console.log("   Логин: admin@vsks.ru | Пароль: Admin123!");
