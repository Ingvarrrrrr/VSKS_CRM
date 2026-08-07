#!/usr/bin/env python3
"""Apply patches to RESTORED server version of RSI bot via SSH."""
import paramiko, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCRIPT = "/opt/analiz-rsi/realtime_rsi_8_of_10_gui_like_backtest.py"
HOST = os.environ.get("REMOTE_HOST", "201.34.139.168")
USER = "root"
PASSWORD = os.environ.get("REMOTE_PASS")
if not PASSWORD:
    print("Задай REMOTE_PASS в окружении", file=sys.stderr)
    sys.exit(1)

def ssh(cmd, timeout=15):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=10)
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors='replace')
    c.close()
    return out

# 1. Backup
print(ssh(f"cp {SCRIPT} {SCRIPT}.pre_patch_v2 && echo BACKUP_OK"))

# 2. Read file
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
sftp = client.open_sftp()
with sftp.file(SCRIPT, 'r') as f:
    content = f.read().decode('utf-8')
print(f"Read {len(content)} bytes")

patches = 0

# === PATCH 1: Add fields to __init__ ===
old = "        self.stop_post_cooldown_until: Optional[datetime] = None"
new = """        self.stop_post_cooldown_until: Optional[datetime] = None

        # Защита от дублирования стоп-заявок (cooldown после операции)
        self._pending_stop_operations: Dict[str, float] = {}
        # Защита от дублирования покупок (cooldown после заявки)
        self._recently_ordered: Dict[str, float] = {}"""
if old in content:
    content = content.replace(old, new, 1)
    patches += 1
    print("PATCH 1: __init__ fields — OK")
else:
    print("PATCH 1: NOT FOUND")

# === PATCH 2: Add helper methods before request_stop ===
old = '    def request_stop(self):\n        """Запрашивает остановку основного цикла"""'
new = '''    def _can_modify_stop(self, stock_uid: str) -> bool:
        """Cooldown 10 сек после последней операции со стопом"""
        import time as _time
        if stock_uid in self._pending_stop_operations:
            if _time.time() - self._pending_stop_operations[stock_uid] < 10:
                return False
            del self._pending_stop_operations[stock_uid]
        return True

    def _mark_stop_operation(self, stock_uid: str):
        """Помечает операцию со стопом для cooldown"""
        import time as _time
        self._pending_stop_operations[stock_uid] = _time.time()

    async def _update_stop_order(self, client, stock_uid: str, quantity_lots: int,
                                  new_stop_price: float, new_sell_price: float,
                                  logger_prefix: str = "    ") -> bool:
        """POST новый стоп -> CANCEL старый. Позиция всегда защищена."""
        position = self.positions.get(stock_uid)
        if not position:
            return False
        old_stop_id = position.get('stop_order_id')
        stock_name = position.get('name', stock_uid[:8])

        new_stop_id = await self._post_stop_order_with_retry(
            client=client, account_id=self.account_id, stock_uid=stock_uid,
            quantity_lots=quantity_lots, stop_price=new_stop_price,
            sell_price=new_sell_price, logger_prefix=logger_prefix)

        if not new_stop_id:
            logger.warning(f"{logger_prefix}Не удалось выставить новый стоп для {stock_name}, старый остаётся")
            return False

        position['stop_order_id'] = new_stop_id
        position['stop_price'] = new_stop_price
        position['sell_price'] = new_sell_price
        self.save_positions()
        self._mark_stop_operation(stock_uid)

        if old_stop_id and old_stop_id != new_stop_id:
            try:
                await client.stop_orders.cancel_stop_order(
                    account_id=self.account_id, stop_order_id=old_stop_id)
                logger.info(f"{logger_prefix}Отменили старый стоп {old_stop_id[:8]}... для {stock_name}")
            except Exception as e:
                logger.warning(f"{logger_prefix}Не удалось отменить старый стоп: {e}")
        return True

    def request_stop(self):
        """Запрашивает остановку основного цикла"""'''
if old in content:
    content = content.replace(old, new, 1)
    patches += 1
    print("PATCH 2: Helper methods — OK")
else:
    print("PATCH 2: NOT FOUND")

# === PATCH 3: Cooldown in ensure_all_positions_have_stop_orders ===
old = """            # Для лимитных заявок проверяем активность на бирже
            if stop_loss_order_type == 'limit':
                if stock_uid not in active_stop_orders_map:"""
new = """            # COOLDOWN: пропускаем если недавно была операция со стопом
            if not self._can_modify_stop(stock_uid):
                continue

            # Для лимитных заявок проверяем активность на бирже
            if stop_loss_order_type == 'limit':
                if stock_uid not in active_stop_orders_map:"""
if old in content:
    content = content.replace(old, new, 1)
    patches += 1
    print("PATCH 3: ensure_stops cooldown — OK")
else:
    print("PATCH 3: NOT FOUND")

# === PATCH 4: INITIAL->BASE: use _update_stop_order ===
old = """                        # Отменяем старый стоп (stop_order_id берём из позиции — в этом блоке он ещё не объявлен ниже)
                        stop_order_id_here = position.get('stop_order_id')
                        if stop_order_id_here and stop_order_id_here in active_stop_order_ids:
                            try:
                                await client.stop_orders.cancel_stop_order(account_id=self.account_id, stop_order_id=stop_order_id_here)
                                logger.info(f"    🛑 Отменили INITIAL стоп {stop_order_id_here[:8]}...")
                            except Exception as e:
                                logger.warning(f"    ⚠️ Не удалось отменить INITIAL стоп: {e}")

                        # Выставляем BASE стоп
                        new_sell_price = base_stop_price - 2 * float(min_price_increment)
                        new_sell_price = round(new_sell_price / float(min_price_increment)) * float(min_price_increment)
                        new_sell_price = round(new_sell_price, 6)

                        new_stop_id = await post_stop_order_async(
                            client,
                            account_id=self.account_id,
                            instrument_id=stock_uid,
                            quantity_lots=quantity_lots,
                            stop_price=base_stop_price,
                            sell_price=new_sell_price,
                            max_attempts=3,
                            logger_prefix="    "
                        )
                        if new_stop_id:
                            position['stop_order_id'] = new_stop_id
                            position['stop_price'] = base_stop_price
                            position['sell_price'] = new_sell_price
                            self.save_positions()
                            logger.info(f"    ✅ Перешли на BASE стоп-лосс: {base_stop_price:.4f}, sell={new_sell_price:.4f}")"""
new = """                        # POST->CANCEL: сначала новый стоп, потом отменяем старый
                        new_sell_price = base_stop_price - 2 * float(min_price_increment)
                        new_sell_price = round(new_sell_price / float(min_price_increment)) * float(min_price_increment)
                        new_sell_price = round(new_sell_price, 6)
                        await self._update_stop_order(client, stock_uid, quantity_lots, base_stop_price, new_sell_price, logger_prefix="    ")"""
if old in content:
    content = content.replace(old, new, 1)
    patches += 1
    print("PATCH 4: INITIAL->BASE — OK")
else:
    print("PATCH 4: NOT FOUND")

# === PATCH 5: Trailing stop: use _update_stop_order ===
old = """                # Сначала ставим новый стоп, затем отменяем старый
                new_trailing_id = await post_stop_order_async(
                    client,
                    account_id=self.account_id,
                    instrument_id=stock_uid,
                    quantity_lots=quantity_lots,
                    stop_price=target_stop_price,
                    sell_price=target_sell_price,
                    max_attempts=3,
                    logger_prefix="    "
                )
                if new_trailing_id:
                    # отменяем старый, если был активен
                    if stop_order_id and stop_order_active:
                        try:
                            await client.stop_orders.cancel_stop_order(account_id=self.account_id, stop_order_id=stop_order_id)
                            logger.info(f"🧹 Отменили старый стоп {stop_order_id[:8]} после успешного трейлинга для {stock_name}")
                        except Exception as e:
                            logger.warning(f"⚠️ Не удалось отменить старый стоп {stop_order_id[:8]} после трейлинга: {e}")
                    position['stop_order_id'] = new_trailing_id
                    position['stop_price'] = target_stop_price
                    position['sell_price'] = target_sell_price
                    position['trailing_price'] = current_price
                    self.save_positions()
                    logger.info(f"✅ Трейлинг стоп обновлён вверх для {stock_name}: {stop_price:.4f} -> {target_stop_price:.4f}")
                else:
                    logger.warning(f"⚠️ Не удалось обновить трейлинг стоп для {stock_name}, оставляем старый")"""
new = """                # POST->CANCEL: сначала новый стоп, потом отменяем старый
                success = await self._update_stop_order(client, stock_uid, quantity_lots,
                    target_stop_price, target_sell_price, logger_prefix="    ")
                if success:
                    position['trailing_price'] = current_price
                    self.save_positions()
                    logger.info(f"✅ Трейлинг стоп обновлён вверх для {stock_name}: {stop_price:.4f} -> {target_stop_price:.4f}")
                else:
                    logger.warning(f"⚠️ Не удалось обновить трейлинг стоп для {stock_name}, оставляем старый")"""
if old in content:
    content = content.replace(old, new, 1)
    patches += 1
    print("PATCH 5: Trailing stop — OK")
else:
    print("PATCH 5: NOT FOUND")

# === PATCH 6: _recently_ordered check ===
old = """                # КРИТИЧНО: Проверяем, нет ли уже активной заявки на покупку для этой акции
                if stock_uid in active_buy_orders:"""
new = """                # ЗАЩИТА ОТ ДУБЛЕЙ: cooldown 120 сек после выставления заявки
                import time as _time
                if stock_uid in self._recently_ordered:
                    if _time.time() - self._recently_ordered[stock_uid] < 120:
                        continue
                    else:
                        del self._recently_ordered[stock_uid]

                # КРИТИЧНО: Проверяем, нет ли уже активной заявки на покупку для этой акции
                if stock_uid in active_buy_orders:"""
if old in content:
    content = content.replace(old, new, 1)
    patches += 1
    print("PATCH 6: _recently_ordered check — OK")
else:
    print("PATCH 6: NOT FOUND")

# === PATCH 7: Mark _recently_ordered after buy ===
old = """                        del self.monitored_stocks[stock_uid]
                        logger.info(f"    ✅ {stock_name} удалена из мониторинга")"""
new = """                        del self.monitored_stocks[stock_uid]
                        self._recently_ordered[stock_uid] = _time.time()
                        logger.info(f"    ✅ {stock_name} удалена из мониторинга")"""
if old in content:
    content = content.replace(old, new, 1)
    patches += 1
    print("PATCH 7: _recently_ordered mark — OK")
else:
    print("PATCH 7: NOT FOUND")

# === Write ===
print(f"\nTotal patches: {patches}/7")
with sftp.file(SCRIPT, 'w') as f:
    f.write(content)
sftp.close()
client.close()
print(f"Written {len(content)} bytes")

# Verify syntax
result = ssh(f"cd /opt/analiz-rsi && python3 -m py_compile {SCRIPT} && echo SYNTAX_OK")
print(result.strip())
