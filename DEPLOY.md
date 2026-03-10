# Деплой VSKS CRM

## Nginx конфиг (ПРАВИЛЬНЫЙ)

```nginx
server {
    listen 80 default_server;
    server_name _;

    # CRM API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
    }

    # CRM assets
    location /assets/ {
        alias /path/to/frontend/dist/assets/;
    }

    # CRM SPA - все пути отдают index.html (ВАЖНО!)
    location / {
        alias /path/to/frontend/dist/;
        try_files $uri /index.html;
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
