# Деплой VSKS CRM

## Nginx конфиг

```nginx
server {
    listen 80 default_server;
    server_name _;

    # CRM API - ВАЖНО: проксировать /api/ на бэкенд
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
    }

    # CRM assets
    location /crm/assets/ {
        alias /path/to/frontend/dist/assets/;
    }
    location /assets/ {
        alias /path/to/frontend/dist/assets/;
    }

    # CRM - статика
    location /crm/ {
        alias /path/to/frontend/dist/;
    }

    # Redirect root to CRM
    location = / {
        return 301 /crm;
    }
}
```

## База данных

- PostgreSQL
- БД: vsks_crm
- Пользователь: vsks_user / vsks_password

## Запуск

```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
DATABASE_URL='postgresql+asyncpg://vsks_user:vsks_password@localhost/vsks_crm' \
./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install --legacy-peer-deps
npm run build
```
