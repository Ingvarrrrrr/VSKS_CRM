#!/bin/sh
# mail/entrypoint.sh — запуск контейнера gala-mail (по образцу FOODSIZO
# server/mail-relay/entrypoint.sh).
#
# При первом старте на свежем сервере /etc/opendkim/keys (volume, см. docker-compose.yml)
# пуст — генерируем DKIM-пару домен galaa.ru / селектор gala и печатаем в лог готовую
# TXT-запись для DNS (см. mail/README.md). При повторных стартах ключ уже есть в volume — НЕ
# перегенерируем (новый ключ потребовал бы новой записи в DNS и сломал бы подпись писем,
# отправленных до того, как запись обновится везде).
#
# Дополнительно пишем /etc/postfix/sender_domain_check (regexp-таблица для
# smtpd_sender_restrictions в main.cf) — она статична (домен зашит в main.cf и здесь одинаково),
# но лежит в entrypoint, а не в образе напрямую, чтобы собрать её postmap-эквивалент (для
# regexp-таблиц postmap не нужен, файл читается как есть).
set -eu

KEY_DIR=/etc/opendkim/keys
SELECTOR=gala
DOMAIN=galaa.ru

# Разрешаем отправителя только из домена galaa.ru (и localhost/postmaster на всякий случай) —
# письмо с любым другим From не пройдёт smtpd_sender_restrictions в main.cf (reject по умолчанию
# после этой таблицы, см. комментарий там же).
cat > /etc/postfix/sender_domain_check <<EOF
/^.+@${DOMAIN}$/    OK
/^.+@.*\.${DOMAIN}$/    OK
EOF

if [ ! -f "$KEY_DIR/$SELECTOR.private" ]; then
  echo "[gala-mail] DKIM-ключ не найден в $KEY_DIR — генерирую новый (селектор $SELECTOR, домен $DOMAIN)"
  mkdir -p "$KEY_DIR"
  opendkim-genkey -b 2048 -d "$DOMAIN" -s "$SELECTOR" -D "$KEY_DIR"
  chown opendkim:opendkim "$KEY_DIR/$SELECTOR.private" "$KEY_DIR/$SELECTOR.txt"
  chmod 600 "$KEY_DIR/$SELECTOR.private"
  echo "[gala-mail] Ключ сгенерирован. НОВАЯ запись DNS (TXT, см. README.md) — внести у регистратора/в DNS-панели:"
else
  echo "[gala-mail] DKIM-ключ уже существует в $KEY_DIR — использую его, не перегенерирую."
  echo "[gala-mail] Действующая запись DNS (TXT, см. README.md), для справки:"
fi

echo "[gala-mail] ---- TXT-запись gala._domainkey.$DOMAIN ----"
cat "$KEY_DIR/$SELECTOR.txt"
echo "[gala-mail] ---- конец записи ----"

# syslog — opendkim/postfix логируют туда (main.cf/opendkim.conf: Syslog yes); без запущенного
# демона rsyslog сообщения просто теряются, но сервисы не падают — это не критично для работы,
# только для диагностики, поэтому ошибку запуска rsyslog не делаем фатальной.
rsyslogd || echo "[gala-mail] rsyslogd не запустился (не критично, логи через docker logs не теряются из-за этого)"

echo "[gala-mail] Запускаю OpenDKIM..."
opendkim -x /etc/opendkim.conf -u opendkim:opendkim -P /var/run/opendkim/opendkim.pid

# Короткая пауза, чтобы milter успел поднять socket 127.0.0.1:8891 до того, как Postfix
# попробует к нему подключиться (smtpd_milters в main.cf).
sleep 1

echo "[gala-mail] Запускаю Postfix (foreground)..."
postfix set-permissions >/dev/null 2>&1 || true
exec postfix start-fg
