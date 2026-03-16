#!/usr/bin/env python3
"""
Apply memory-leak fixes to realtime_rsi_8_of_10_gui_like_backtest.py on the server.
All patches are applied via string replacement on the original file.
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import paramiko

HOST = "85.239.53.155"
USER = "root"
PASSWORD = os.environ.get("REMOTE_PASS", "")
SCRIPT = "/opt/analiz-rsi/realtime_rsi_8_of_10_gui_like_backtest.py"

def ssh_exec(cmd, timeout=60):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    rc = stdout.channel.recv_exit_status()
    client.close()
    return out, err, rc

def ssh_write_file(remote_path, content):
    """Write content to a remote file via SFTP."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
    sftp = client.open_sftp()
    with sftp.file(remote_path, 'w') as f:
        f.write(content)
    sftp.close()
    client.close()

def main():
    # Step 1: Backup original
    print("1. Creating backup...")
    out, err, rc = ssh_exec(f"cp {SCRIPT} {SCRIPT}.backup.$(date +%Y%m%d_%H%M%S) && echo OK")
    print(out.strip())

    # Step 2: Read current file
    print("2. Reading original script...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
    sftp = client.open_sftp()
    with sftp.file(SCRIPT, 'r') as f:
        content = f.read().decode('utf-8')
    sftp.close()
    client.close()
    # Normalize line endings to \n for matching, will restore \r\n at the end
    had_crlf = '\r\n' in content
    if had_crlf:
        content = content.replace('\r\n', '\n')
    print(f"   Read {len(content)} bytes, {content.count(chr(10))} lines (CRLF: {had_crlf})")

    patches_applied = 0

    # =====================================================================
    # PATCH 1: Make tkinter import conditional (headless server safe)
    # =====================================================================
    old_tkinter = """# GUI для отдельных окон мониторинга
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText"""

    new_tkinter = """# GUI для отдельных окон мониторинга (условный импорт для headless серверов)
import os as _os
_HAS_DISPLAY = bool(_os.environ.get('DISPLAY') or _os.name == 'nt')
if _HAS_DISPLAY:
    try:
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
        from tkinter.scrolledtext import ScrolledText
        _TK_AVAILABLE = True
    except ImportError:
        _TK_AVAILABLE = False
else:
    _TK_AVAILABLE = False
    # Заглушки чтобы код не падал при обращении к tk.*
    tk = None
    ttk = None
    ScrolledText = None"""

    if old_tkinter in content:
        content = content.replace(old_tkinter, new_tkinter)
        patches_applied += 1
        print("   PATCH 1: tkinter conditional import — applied")
    else:
        print("   PATCH 1: tkinter — NOT FOUND (already patched?)")

    # =====================================================================
    # PATCH 2: RotatingFileHandler instead of plain FileHandler
    # =====================================================================
    old_logging = """logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8')
        # StreamHandler убран - логи только в файл
    ]
)"""

    new_logging = """from logging.handlers import RotatingFileHandler as _RFH
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        _RFH(log_file, maxBytes=50*1024*1024, backupCount=3, encoding='utf-8')
        # RotatingFileHandler: макс 50 МБ, 3 backup-файла
    ]
)"""

    if old_logging in content:
        content = content.replace(old_logging, new_logging)
        patches_applied += 1
        print("   PATCH 2: RotatingFileHandler — applied")
    else:
        print("   PATCH 2: RotatingFileHandler — NOT FOUND")

    # =====================================================================
    # PATCH 3: In-memory candle cache for StockDataManager
    # =====================================================================
    old_sdm_init = """class StockDataManager:
    \"\"\"Управляет CSV файлами с данными для каждой акции\"\"\"

    def __init__(self, data_dir: str = 'realtime_stock_data'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.max_candles = 100
        self.min_candles_for_analysis = 10"""

    new_sdm_init = """class StockDataManager:
    \"\"\"Управляет CSV файлами с данными для каждой акции (с in-memory кэшем)\"\"\"

    def __init__(self, data_dir: str = 'realtime_stock_data'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.max_candles = 100
        self.min_candles_for_analysis = 10
        self._cache: Dict[str, pd.DataFrame] = {}  # in-memory cache: key -> DataFrame
        self._cache_dirty: set = set()  # keys that need to be written to disk
        self._flush_counter = 0  # counter for periodic flush"""

    if old_sdm_init in content:
        content = content.replace(old_sdm_init, new_sdm_init)
        patches_applied += 1
        print("   PATCH 3a: StockDataManager cache init — applied")
    else:
        print("   PATCH 3a: StockDataManager cache init — NOT FOUND")

    # Replace load_candles to use cache
    old_load = """    def load_candles(self, stock_uid: str, interval_minutes: int) -> pd.DataFrame:
        \"\"\"Загружает свечи из CSV файла\"\"\"
        csv_path = self.get_csv_path(stock_uid, interval_minutes)

        if not csv_path.exists():
            return pd.DataFrame()

        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            df['time'] = pd.to_datetime(df['time'])
            return df.sort_values('time').reset_index(drop=True)
        except Exception as e:
            logger.error(f"Ошибка загрузки данных для {stock_uid}: {e}")
            return pd.DataFrame()"""

    new_load = """    def load_candles(self, stock_uid: str, interval_minutes: int) -> pd.DataFrame:
        \"\"\"Загружает свечи из кэша (или CSV при первом обращении)\"\"\"
        cache_key = f"{stock_uid}_{interval_minutes}"
        if cache_key in self._cache:
            return self._cache[cache_key].copy()

        csv_path = self.get_csv_path(stock_uid, interval_minutes)
        if not csv_path.exists():
            return pd.DataFrame()

        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            df['time'] = pd.to_datetime(df['time'])
            df = df.sort_values('time').reset_index(drop=True)
            self._cache[cache_key] = df
            return df.copy()
        except Exception as e:
            logger.error(f"Ошибка загрузки данных для {stock_uid}: {e}")
            return pd.DataFrame()"""

    if old_load in content:
        content = content.replace(old_load, new_load)
        patches_applied += 1
        print("   PATCH 3b: load_candles with cache — applied")
    else:
        print("   PATCH 3b: load_candles — NOT FOUND")

    # Replace save_candles to use cache
    old_save = """    def save_candles(self, stock_uid: str, interval_minutes: int, candles: pd.DataFrame):
        \"\"\"Сохраняет свечи в CSV файл (максимум max_candles)\"\"\"
        csv_path = self.get_csv_path(stock_uid, interval_minutes)

        if len(candles) > self.max_candles:
            candles = candles.tail(self.max_candles).copy()

        candles = candles.sort_values('time').reset_index(drop=True)
        candles.to_csv(csv_path, index=False, encoding='utf-8-sig')"""

    new_save = """    def save_candles(self, stock_uid: str, interval_minutes: int, candles: pd.DataFrame):
        \"\"\"Сохраняет свечи в кэш и помечает для записи на диск\"\"\"
        if len(candles) > self.max_candles:
            candles = candles.tail(self.max_candles).copy()

        candles = candles.sort_values('time').reset_index(drop=True)
        cache_key = f"{stock_uid}_{interval_minutes}"
        self._cache[cache_key] = candles
        self._cache_dirty.add(cache_key)

        # Сбрасываем на диск каждые 12 вызовов (~1 раз в минуту при 5с цикле)
        self._flush_counter += 1
        if self._flush_counter >= 12:
            self.flush_to_disk()
            self._flush_counter = 0

    def flush_to_disk(self):
        \"\"\"Записывает все грязные кэши на диск\"\"\"
        for cache_key in list(self._cache_dirty):
            parts = cache_key.rsplit('_', 1)
            if len(parts) == 2:
                stock_uid, interval_str = parts
                try:
                    csv_path = self.get_csv_path(stock_uid, int(interval_str))
                    self._cache[cache_key].to_csv(csv_path, index=False, encoding='utf-8-sig')
                except Exception as e:
                    logger.error(f"Ошибка записи кэша {cache_key} на диск: {e}")
        self._cache_dirty.clear()"""

    if old_save in content:
        content = content.replace(old_save, new_save)
        patches_applied += 1
        print("   PATCH 3c: save_candles with cache — applied")
    else:
        print("   PATCH 3c: save_candles — NOT FOUND")

    # Replace needs_more_data to use cache
    old_needs = """    def needs_more_data(self, stock_uid: str, interval_minutes: int) -> bool:
        \"\"\"Проверяет, нужно ли запросить больше данных\"\"\"
        df = self.load_candles(stock_uid, interval_minutes)
        return len(df) < self.min_candles_for_analysis"""

    new_needs = """    def needs_more_data(self, stock_uid: str, interval_minutes: int) -> bool:
        \"\"\"Проверяет, нужно ли запросить больше данных\"\"\"
        cache_key = f"{stock_uid}_{interval_minutes}"
        if cache_key in self._cache:
            return len(self._cache[cache_key]) < self.min_candles_for_analysis
        df = self.load_candles(stock_uid, interval_minutes)
        return len(df) < self.min_candles_for_analysis"""

    if old_needs in content:
        content = content.replace(old_needs, new_needs)
        patches_applied += 1
        print("   PATCH 3d: needs_more_data with cache — applied")
    else:
        print("   PATCH 3d: needs_more_data — NOT FOUND")

    # Replace add_candle to use cache
    old_add = """    def add_candle(self, stock_uid: str, interval_minutes: int, candle: Dict):
        \"\"\"Добавляет новую свечу к существующим данным\"\"\"
        df = self.load_candles(stock_uid, interval_minutes)

        new_row = pd.DataFrame([candle])
        new_row['time'] = pd.to_datetime(new_row['time'])

        if len(df) > 0:
            df = pd.concat([df, new_row], ignore_index=True)
            df = df.drop_duplicates(subset=['time'], keep='last')
        else:
            df = new_row

        self.save_candles(stock_uid, interval_minutes, df)"""

    new_add = """    def add_candle(self, stock_uid: str, interval_minutes: int, candle: Dict):
        \"\"\"Добавляет новую свечу к кэшу (без чтения CSV)\"\"\"
        cache_key = f"{stock_uid}_{interval_minutes}"
        if cache_key in self._cache:
            df = self._cache[cache_key]
        else:
            df = self.load_candles(stock_uid, interval_minutes)

        new_row = pd.DataFrame([candle])
        new_row['time'] = pd.to_datetime(new_row['time'])

        if len(df) > 0:
            df = pd.concat([df, new_row], ignore_index=True)
            df = df.drop_duplicates(subset=['time'], keep='last')
        else:
            df = new_row

        self.save_candles(stock_uid, interval_minutes, df)"""

    if old_add in content:
        content = content.replace(old_add, new_add)
        patches_applied += 1
        print("   PATCH 3e: add_candle with cache — applied")
    else:
        print("   PATCH 3e: add_candle — NOT FOUND")

    # =====================================================================
    # PATCH 4: RSI caching — add cache dict to trader __init__
    # =====================================================================
    old_init_dm = """        self.data_manager = StockDataManager()"""
    new_init_dm = """        self.data_manager = StockDataManager()
        # RSI cache: {stock_uid: {'candle_count': N, 'rsi_values': pd.Series}}
        self._rsi_cache: Dict[str, Dict] = {}"""

    if old_init_dm in content:
        content = content.replace(old_init_dm, new_init_dm, 1)
        patches_applied += 1
        print("   PATCH 4a: RSI cache dict in __init__ — applied")
    else:
        print("   PATCH 4a: RSI cache init — NOT FOUND")

    # =====================================================================
    # PATCH 5: Cap stats['trades'] to 500 entries
    # =====================================================================
    # After record_buy appends to trades, cap the list
    old_record_buy_save = """        self.stats['trades'].append({
            'stock_name': stock_name,
            'stock_uid': stock_uid,
            'buy_price': buy_price,
            'buy_time': datetime.now(moscow_tz).isoformat(),
            'quantity': quantity,
            'buy_amount': buy_amount,  # Полная стоимость покупки
            'sell_price': None,
            'sell_time': None,
            'sell_amount': None,  # Полная стоимость продажи
            'profit': None,
            'rsi_value': rsi_value,  # RSI на момент покупки
            'interval': interval  # Интервал в минутах
        })
        self.save_stats()"""

    new_record_buy_save = """        self.stats['trades'].append({
            'stock_name': stock_name,
            'stock_uid': stock_uid,
            'buy_price': buy_price,
            'buy_time': datetime.now(moscow_tz).isoformat(),
            'quantity': quantity,
            'buy_amount': buy_amount,  # Полная стоимость покупки
            'sell_price': None,
            'sell_time': None,
            'sell_amount': None,  # Полная стоимость продажи
            'profit': None,
            'rsi_value': rsi_value,  # RSI на момент покупки
            'interval': interval  # Интервал в минутах
        })
        # Ограничиваем список сделок: храним все открытые + последние 200 закрытых
        open_trades = [t for t in self.stats['trades'] if t.get('sell_price') is None]
        closed_trades = [t for t in self.stats['trades'] if t.get('sell_price') is not None]
        if len(closed_trades) > 200:
            closed_trades = closed_trades[-200:]
        self.stats['trades'] = closed_trades + open_trades
        self.save_stats()"""

    if old_record_buy_save in content:
        content = content.replace(old_record_buy_save, new_record_buy_save)
        patches_applied += 1
        print("   PATCH 5: Cap trades list to 200 closed + open — applied")
    else:
        print("   PATCH 5: Cap trades — NOT FOUND")

    # =====================================================================
    # PATCH 6: save_to_csv — true append mode, limit total rows
    # =====================================================================
    old_csv_save = """            # Записываем в CSV (append mode)
            df = pd.DataFrame(rows)
            if csv_path.exists():
                # Проверяем, что файл не пустой
                file_size = csv_path.stat().st_size
                if file_size > 0:
                    try:
                        # Пытаемся прочитать файл
                        existing_df = pd.read_csv(csv_path, encoding='utf-8-sig')
                        # Проверяем, что файл содержит данные
                        if not existing_df.empty and len(existing_df.columns) > 0:
                            df = pd.concat([existing_df, df], ignore_index=True)
                        # Если файл пустой или невалидный, используем только новые данные
                    except (pd.errors.EmptyDataError, pd.errors.ParserError) as e:
                        logger.warning(f"CSV файл поврежден или пуст, создаем новый: {e}")
                        # Продолжаем с новыми данными
                # Если файл пустой (размер = 0), используем только новые данные

            df.to_csv(csv_path, index=False, encoding='utf-8-sig')"""

    new_csv_save = """            # Записываем в CSV (true append mode — НЕ перечитываем весь файл!)
            df = pd.DataFrame(rows)
            if csv_path.exists() and csv_path.stat().st_size > 0:
                # Append без перечитывания файла
                df.to_csv(csv_path, mode='a', header=False, index=False, encoding='utf-8-sig')
            else:
                # Первая запись — с заголовками
                df.to_csv(csv_path, index=False, encoding='utf-8-sig')

            # Ротация: если файл > 10 МБ, обрезаем до последних 5000 строк
            try:
                if csv_path.stat().st_size > 10 * 1024 * 1024:
                    old_df = pd.read_csv(csv_path, encoding='utf-8-sig')
                    old_df.tail(5000).to_csv(csv_path, index=False, encoding='utf-8-sig')
                    logger.info(f"CSV ротация: обрезано до 5000 строк")
            except Exception:
                pass"""

    if old_csv_save in content:
        content = content.replace(old_csv_save, new_csv_save)
        patches_applied += 1
        print("   PATCH 6: CSV append mode + rotation — applied")
    else:
        print("   PATCH 6: CSV save — NOT FOUND")

    # =====================================================================
    # PATCH 7: save_to_excel — limit rows, don't re-read whole file every time
    # =====================================================================
    old_excel_read = """            # Проверяем существование файла
            file_exists = excel_path.exists()

            # Создаем или обновляем Excel файл
            if file_exists:
                # Читаем существующие данные
                try:
                    existing_summary = pd.read_excel(excel_path, sheet_name='Общая статистика')
                    existing_trades = pd.read_excel(excel_path, sheet_name='Сделки')
                except Exception as e:
                    logger.warning(f"Ошибка чтения существующего Excel файла: {e}, создаем новый")
                    existing_summary = pd.DataFrame()
                    existing_trades = pd.DataFrame()
            else:
                existing_summary = pd.DataFrame()
                existing_trades = pd.DataFrame()

            # Добавляем новые данные к существующим
            df_summary_new = pd.DataFrame(summary_data)
            df_summary = pd.concat([existing_summary, df_summary_new], ignore_index=True)

            if trades_data:
                df_trades_new = pd.DataFrame(trades_data)
                df_trades = pd.concat([existing_trades, df_trades_new], ignore_index=True)
            else:
                df_trades = existing_trades

            # Сохраняем в Excel файл
            with pd.ExcelWriter(excel_path, engine='openpyxl', mode='w') as writer:
                df_summary.to_excel(writer, sheet_name='Общая статистика', index=False)
                if not df_trades.empty:
                    df_trades.to_excel(writer, sheet_name='Сделки', index=False)"""

    new_excel_read = """            # Проверяем существование файла
            file_exists = excel_path.exists()

            # Создаем или обновляем Excel файл
            if file_exists:
                try:
                    existing_summary = pd.read_excel(excel_path, sheet_name='Общая статистика')
                    existing_trades = pd.read_excel(excel_path, sheet_name='Сделки')
                except Exception as e:
                    logger.warning(f"Ошибка чтения Excel: {e}, создаем новый")
                    existing_summary = pd.DataFrame()
                    existing_trades = pd.DataFrame()
            else:
                existing_summary = pd.DataFrame()
                existing_trades = pd.DataFrame()

            df_summary_new = pd.DataFrame(summary_data)
            df_summary = pd.concat([existing_summary, df_summary_new], ignore_index=True)
            # Ограничиваем summary до последних 2000 строк
            if len(df_summary) > 2000:
                df_summary = df_summary.tail(2000).reset_index(drop=True)

            if trades_data:
                df_trades_new = pd.DataFrame(trades_data)
                df_trades = pd.concat([existing_trades, df_trades_new], ignore_index=True)
            else:
                df_trades = existing_trades
            # Ограничиваем trades до последних 2000 строк
            if len(df_trades) > 2000:
                df_trades = df_trades.tail(2000).reset_index(drop=True)

            with pd.ExcelWriter(excel_path, engine='openpyxl', mode='w') as writer:
                df_summary.to_excel(writer, sheet_name='Общая статистика', index=False)
                if not df_trades.empty:
                    df_trades.to_excel(writer, sheet_name='Сделки', index=False)"""

    if old_excel_read in content:
        content = content.replace(old_excel_read, new_excel_read)
        patches_applied += 1
        print("   PATCH 7: Excel row limit (2000) — applied")
    else:
        print("   PATCH 7: Excel save — NOT FOUND")

    # =====================================================================
    # PATCH 8: Batch save_positions — add dirty flag
    # =====================================================================
    old_save_pos = """    def save_positions(self):
        \"\"\"Сохраняет позиции в JSON файл\"\"\"
        try:
            # Преобразуем datetime объекты в строки для JSON
            positions_to_save = {}
            for uid, position in self.positions.items():
                pos_copy = position.copy()
                # Преобразуем datetime в строку
                if 'buy_time' in pos_copy and isinstance(pos_copy['buy_time'], datetime):
                    pos_copy['buy_time'] = pos_copy['buy_time'].isoformat()
                if 'buy_candle_time' in pos_copy and isinstance(pos_copy['buy_candle_time'], datetime):
                    pos_copy['buy_candle_time'] = pos_copy['buy_candle_time'].isoformat()
                if 'stop_loss_candle_time' in pos_copy and isinstance(pos_copy['stop_loss_candle_time'], datetime):
                    pos_copy['stop_loss_candle_time'] = pos_copy['stop_loss_candle_time'].isoformat()
                positions_to_save[uid] = pos_copy

            with open(self.positions_file, 'w', encoding='utf-8') as f:
                json.dump(positions_to_save, f, ensure_ascii=False, indent=2, default=str)
            logger.debug(f"💾 Позиции сохранены: {len(positions_to_save)} позиций")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения позиций: {e}")"""

    new_save_pos = """    def save_positions(self, force: bool = False):
        \"\"\"Сохраняет позиции в JSON файл (с батчингом — реально пишет раз в 10 вызовов или при force)\"\"\"
        if not hasattr(self, '_save_pos_counter'):
            self._save_pos_counter = 0
        self._save_pos_counter += 1

        # Пишем на диск только каждые 10 вызовов или при force
        if not force and self._save_pos_counter % 10 != 0:
            return

        try:
            positions_to_save = {}
            for uid, position in self.positions.items():
                pos_copy = position.copy()
                if 'buy_time' in pos_copy and isinstance(pos_copy['buy_time'], datetime):
                    pos_copy['buy_time'] = pos_copy['buy_time'].isoformat()
                if 'buy_candle_time' in pos_copy and isinstance(pos_copy['buy_candle_time'], datetime):
                    pos_copy['buy_candle_time'] = pos_copy['buy_candle_time'].isoformat()
                if 'stop_loss_candle_time' in pos_copy and isinstance(pos_copy['stop_loss_candle_time'], datetime):
                    pos_copy['stop_loss_candle_time'] = pos_copy['stop_loss_candle_time'].isoformat()
                positions_to_save[uid] = pos_copy

            with open(self.positions_file, 'w', encoding='utf-8') as f:
                json.dump(positions_to_save, f, ensure_ascii=False, indent=2, default=str)
            logger.debug(f"💾 Позиции сохранены: {len(positions_to_save)} позиций")
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения позиций: {e}")"""

    if old_save_pos in content:
        content = content.replace(old_save_pos, new_save_pos)
        patches_applied += 1
        print("   PATCH 8: Batch save_positions (1 write per 10 calls) — applied")
    else:
        print("   PATCH 8: save_positions — NOT FOUND")

    # =====================================================================
    # PATCH 9: Guard init_gui for headless
    # =====================================================================
    old_init_gui = """        # Инициализируем GUI окна (если используется внутренний GUI трейдера)
        try:
            self.init_gui()
        except Exception as e:
            logger.warning(f"⚠️ Не удалось инициализировать внутренний GUI трейдера: {e}")"""

    new_init_gui = """        # Инициализируем GUI окна только если есть дисплей
        if _TK_AVAILABLE:
            try:
                self.init_gui()
            except Exception as e:
                logger.warning(f"⚠️ Не удалось инициализировать внутренний GUI трейдера: {e}")
        else:
            logger.info("🖥️ Headless режим — GUI отключен")"""

    if old_init_gui in content:
        content = content.replace(old_init_gui, new_init_gui)
        patches_applied += 1
        print("   PATCH 9: Guard init_gui for headless — applied")
    else:
        print("   PATCH 9: init_gui guard — NOT FOUND")

    # =====================================================================
    # PATCH 10: Force save positions on stop
    # =====================================================================
    old_stop_stats = """                print("\\n" + "=" * 80)
                print("🛑 ОСТАНОВКА МОДУЛЯ")
                print("=" * 80)
                self.stats.print_stats(detailed=True)"""

    new_stop_stats = """                print("\\n" + "=" * 80)
                print("🛑 ОСТАНОВКА МОДУЛЯ")
                print("=" * 80)
                self.save_positions(force=True)  # Гарантируем запись позиций при остановке
                if hasattr(self.data_manager, 'flush_to_disk'):
                    self.data_manager.flush_to_disk()  # Записываем все кэши свечей
                self.stats.print_stats(detailed=True)"""

    if old_stop_stats in content:
        content = content.replace(old_stop_stats, new_stop_stats)
        patches_applied += 1
        print("   PATCH 10: Force save on stop — applied")
    else:
        print("   PATCH 10: Force save on stop — NOT FOUND")

    # =====================================================================
    # Write patched file
    # =====================================================================
    print(f"\n   Total patches applied: {patches_applied}")

    if patches_applied == 0:
        print("   No patches applied! File may already be patched or structure changed.")
        return

    # Restore original line endings
    if had_crlf:
        content = content.replace('\n', '\r\n')
    print(f"3. Writing patched file ({len(content)} bytes)...")
    ssh_write_file(SCRIPT, content)
    print("   Done!")

    # Step 4: Verify syntax
    print("4. Verifying Python syntax...")
    out, err, rc = ssh_exec(f"cd /opt/analiz-rsi && python3 -m py_compile {SCRIPT} && echo 'Syntax OK'")
    print(f"   {out.strip()}")
    if rc != 0:
        print(f"   ERROR: {err.strip()}")
        print("   Restoring backup...")
        ssh_exec(f"cp {SCRIPT}.backup.* {SCRIPT}")
        return

    print("\n✅ All patches applied successfully!")
    print(f"   Backup saved as {SCRIPT}.backup.*")
    print("   Script NOT restarted — do it manually when ready.")


if __name__ == "__main__":
    main()
