# mail/Dockerfile — контейнер gala-mail: ТОЛЬКО отправка почты (Postfix) + подпись DKIM
# (OpenDKIM), по образцу FOODSIZO (server/mail-relay/, .planning/TWO_SIDED_ACCOUNTS_PLAN.md
# «Часть 2. Почта» в том проекте). Входящая почта не нужна и не принимается. Порт 25 слушает
# ТОЛЬКО внутри docker-сети этого проекта (docker-compose.yml: сервис `mail` без `ports:`) —
# наружу НЕ публикуется (правило №4 CLAUDE.md: наружу только 80/443+22).
#
# Debian slim — та же причина, что в FOODSIZO: в Alpine пакет postfix урезан, debian даёт
# одинаковые пакеты годами.
FROM debian:12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       postfix \
       opendkim \
       opendkim-tools \
       rsyslog \
       ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/postfix/main.cf

# Конфиги — см. ./main.cf (Postfix) и ./opendkim.conf (OpenDKIM). entrypoint.sh на каждом
# старте: генерирует DKIM-ключ в volume /etc/opendkim/keys, если его там ещё нет (первый
# запуск на свежем сервере), собирает key table / signing table, печатает готовую TXT-запись
# в лог и запускает rsyslog + opendkim + postfix.
COPY main.cf /etc/postfix/main.cf
COPY opendkim.conf /etc/opendkim.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && mkdir -p /etc/opendkim/keys \
    && chown -R opendkim:opendkim /etc/opendkim

EXPOSE 25

ENTRYPOINT ["/entrypoint.sh"]
