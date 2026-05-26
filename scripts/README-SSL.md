# SSL — gaaala.duckdns.org (Phase 30-07)

Let's Encrypt сертификат через DNS-01 challenge (DuckDNS API).
Не требует открытия порта 80 для ACME, работает за NAT/CDN.

## Архитектура

```
nginx (80/443) ─── volume:letsencrypt ─── certbot (DNS-01 via DuckDNS)
       │                                       │
       │                                       └─ renew каждые 12ч
       └─ перечитывает конфиг каждые 6ч (новые cert)
```

## Первый выпуск (один раз на проде)

### 1. Положить токен в `.env` на сервере

```bash
ssh root@85.239.53.155
cd /opt/vsks-crm
echo 'DUCKDNS_TOKEN=НОВЫЙ_ТОКЕН_DUCKDNS' >> .env
```

⚠️ **Сгенерируй НОВЫЙ токен** в DuckDNS (старый засветился в чате).

### 2. Pull свежий код + перезапуск

```bash
cd /opt/vsks-crm
git pull origin claude
docker compose pull        # подтянуть certbot/nginx образы
docker compose up -d       # пересоздаст nginx (с 443 портом) и поднимет certbot
```

### 3. Проверить DNS

```bash
dig +short gaaala.duckdns.org @8.8.8.8
# должно быть: 85.239.53.155
```

Если IP другой — обновить:
```bash
. .env  # подгрузит DUCKDNS_TOKEN
curl "https://www.duckdns.org/update?domains=gaaala&token=$DUCKDNS_TOKEN&ip=85.239.53.155"
# ожидаем: OK
```

### 4. Запустить первый выпуск

**Сначала на staging** (чтобы не словить rate-limit от LE):
```bash
bash scripts/setup-ssl.sh --staging
```

Если staging успешен — выпустить настоящий:
```bash
# Удалить staging cert
docker compose run --rm --entrypoint sh certbot -c "rm -rf /etc/letsencrypt/live/gaaala.duckdns.org /etc/letsencrypt/archive/gaaala.duckdns.org /etc/letsencrypt/renewal/gaaala.duckdns.org.conf"

# Реальный выпуск
bash scripts/setup-ssl.sh
```

### 5. Smoke

```bash
curl -I https://gaaala.duckdns.org
# HTTP/2 200
# strict-transport-security: max-age=15768000

openssl s_client -connect gaaala.duckdns.org:443 -servername gaaala.duckdns.org </dev/null 2>/dev/null | openssl x509 -noout -issuer -dates
# issuer=C = US, O = Let's Encrypt, CN = R3 (или ISRG)
```

## Renewal

Certbot контейнер крутится в фоне, каждые 12 часов вызывает `certbot renew`.
Если до expiry осталось <30 дней — обновит. nginx перечитывает конфиг каждые 6 часов.

Логи:
```bash
docker compose logs --tail 30 certbot
```

## Откат

Если что-то сломалось — оставить только HTTP:
```bash
# Удалить ports/volumes 443 и certbot service из docker-compose.yml
# Убрать server-блок 443 из nginx.conf
git revert <hash_phase_30_07>
docker compose up -d
```

IP-доступ `http://85.239.53.155` продолжает работать независимо.

## Troubleshooting

| Симптом | Что смотреть |
|---|---|
| nginx не стартует, `cert not found` | Сертификат ещё не выпущен — запустить `setup-ssl.sh`; пока nginx можно поднять с закомментированным 443-блоком |
| certbot падает с `Invalid token` | Проверить `.env` на сервере, токен из DuckDNS UI |
| `DNS problem: NXDOMAIN` | A-запись не propagated, подождать 5-10 мин |
| Rate limit LE | Использовать `--staging`, потом переключиться |
