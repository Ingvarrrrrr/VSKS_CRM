#!/usr/bin/env python3
"""Patch script to run DIRECTLY on the server."""

SCRIPT = "/opt/analiz-rsi/realtime_rsi_8_of_10_gui_like_backtest.py"

import re

with open(SCRIPT, 'r', encoding='utf-8') as f:
    lines = f.readlines()

content = ''.join(lines)
# Normalize to \n for matching
content = content.replace('\r\n', '\n')

patches = 0

# ── PATCH A: StockDataManager.__init__ — add cache fields ──
# Find "self.min_candles_for_analysis = 10" inside StockDataManager and add cache after it
old = "        self.min_candles_for_analysis = 10"
new = """        self.min_candles_for_analysis = 10
        self._cache = {}  # in-memory cache: cache_key -> DataFrame
        self._cache_dirty = set()  # keys needing disk write
        self._flush_counter = 0"""
if old in content:
    content = content.replace(old, new, 1)
    patches += 1
    print("PATCH A: StockDataManager cache init — OK")

# ── PATCH B: load_candles — use cache ──
# Replace the body of load_candles
old_load = '''    def load_candles(self, stock_uid: str, interval_minutes: int) -> pd.DataFrame:
        """Загружает свечи из CSV файла"""
        csv_path = self.get_csv_path(stock_uid, interval_minutes)

        if not csv_path.exists():
            return pd.DataFrame()

        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            df['time'] = pd.to_datetime(df['time'])
            return df.sort_values('time').reset_index(drop=True)
        except Exception as e:
            logger.error(f"Ошибка загрузки данных для {stock_uid}: {e}")
            return pd.DataFrame()'''

new_load = '''    def load_candles(self, stock_uid: str, interval_minutes: int) -> pd.DataFrame:
        """Загружает свечи из кэша (или CSV при первом обращении)"""
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
            return pd.DataFrame()'''

if old_load in content:
    content = content.replace(old_load, new_load, 1)
    patches += 1
    print("PATCH B: load_candles cache — OK")
else:
    # Try with trailing spaces on blank lines
    old_load2 = old_load.replace("\n        \n", "\n\n").replace("\n    \n", "\n\n")
    if old_load2 in content:
        content = content.replace(old_load2, new_load, 1)
        patches += 1
        print("PATCH B: load_candles cache (alt whitespace) — OK")
    else:
        print("PATCH B: load_candles — NOT FOUND, trying regex")
        # Use regex to match the function
        pattern = r'(    def load_candles\(self, stock_uid: str, interval_minutes: int\) -> pd\.DataFrame:\n)'
        pattern += r'(        """[^"]*"""\n)'
        pattern += r'((?:        .*\n)*?)'
        pattern += r'(            return pd\.DataFrame\(\)\n)'
        m = re.search(pattern, content)
        if m:
            full_match = m.group(0)
            content = content.replace(full_match, new_load + '\n', 1)
            patches += 1
            print("PATCH B: load_candles cache (regex) — OK")
        else:
            print("PATCH B: load_candles — FAILED")

# ── PATCH C: save_candles — use cache + periodic flush ──
old_save = '''    def save_candles(self, stock_uid: str, interval_minutes: int, candles: pd.DataFrame):
        """Сохраняет свечи в CSV файл (максимум max_candles)"""
        csv_path = self.get_csv_path(stock_uid, interval_minutes)

        if len(candles) > self.max_candles:
            candles = candles.tail(self.max_candles).copy()

        candles = candles.sort_values('time').reset_index(drop=True)
        candles.to_csv(csv_path, index=False, encoding='utf-8-sig')'''

new_save = '''    def save_candles(self, stock_uid: str, interval_minutes: int, candles: pd.DataFrame):
        """Сохраняет свечи в кэш, записывает на диск каждые 12 вызовов"""
        if len(candles) > self.max_candles:
            candles = candles.tail(self.max_candles).copy()
        candles = candles.sort_values('time').reset_index(drop=True)
        cache_key = f"{stock_uid}_{interval_minutes}"
        self._cache[cache_key] = candles
        self._cache_dirty.add(cache_key)
        self._flush_counter += 1
        if self._flush_counter >= 12:
            self.flush_to_disk()
            self._flush_counter = 0

    def flush_to_disk(self):
        """Записывает все грязные кэши на диск"""
        for cache_key in list(self._cache_dirty):
            parts = cache_key.rsplit('_', 1)
            if len(parts) == 2:
                stock_uid, interval_str = parts
                try:
                    csv_path = self.get_csv_path(stock_uid, int(interval_str))
                    self._cache[cache_key].to_csv(csv_path, index=False, encoding='utf-8-sig')
                except Exception as e:
                    logger.error(f"Ошибка записи кэша {cache_key}: {e}")
        self._cache_dirty.clear()'''

if old_save in content:
    content = content.replace(old_save, new_save, 1)
    patches += 1
    print("PATCH C: save_candles cache + flush — OK")
else:
    print("PATCH C: save_candles — NOT FOUND")

# ── PATCH D: add_candle — use cache ──
old_add = '        df = self.load_candles(stock_uid, interval_minutes)\n        \n        new_row = pd.DataFrame([candle])'
new_add = '        cache_key = f"{stock_uid}_{interval_minutes}"\n        if cache_key in self._cache:\n            df = self._cache[cache_key]\n        else:\n            df = self.load_candles(stock_uid, interval_minutes)\n        \n        new_row = pd.DataFrame([candle])'

if old_add in content:
    content = content.replace(old_add, new_add, 1)
    patches += 1
    print("PATCH D: add_candle cache lookup — OK")
else:
    # Try without trailing spaces
    old_add2 = '        df = self.load_candles(stock_uid, interval_minutes)\n\n        new_row = pd.DataFrame([candle])'
    if old_add2 in content:
        content = content.replace(old_add2, new_add, 1)
        patches += 1
        print("PATCH D: add_candle cache (alt) — OK")
    else:
        print("PATCH D: add_candle — NOT FOUND")

# ── PATCH E: save_to_csv — true append mode ──
old_csv = '                        existing_df = pd.read_csv(csv_path, encoding=\'utf-8-sig\')\n                        # Проверяем, что файл содержит данные\n                        if not existing_df.empty and len(existing_df.columns) > 0:\n                            df = pd.concat([existing_df, df], ignore_index=True)'
new_csv = '                        pass  # OPTIMIZED: skip re-reading, use append mode below'

if old_csv in content:
    content = content.replace(old_csv, new_csv, 1)
    patches += 1
    print("PATCH E1: Remove CSV re-read — OK")
else:
    print("PATCH E1: CSV re-read — NOT FOUND")

# Replace the final write to use append mode
old_csv_write = "            df.to_csv(csv_path, index=False, encoding='utf-8-sig')\n            logger.debug(f\"💾 Статистика сохранена в CSV: {csv_file}\")"
new_csv_write = """            if csv_path.exists() and csv_path.stat().st_size > 0:
                df.to_csv(csv_path, mode='a', header=False, index=False, encoding='utf-8-sig')
            else:
                df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            # Ротация: если > 10 МБ, обрезаем
            try:
                if csv_path.stat().st_size > 10 * 1024 * 1024:
                    old_df = pd.read_csv(csv_path, encoding='utf-8-sig')
                    old_df.tail(5000).to_csv(csv_path, index=False, encoding='utf-8-sig')
            except Exception:
                pass
            logger.debug(f"💾 Статистика сохранена в CSV: {csv_file}")"""

if old_csv_write in content:
    content = content.replace(old_csv_write, new_csv_write, 1)
    patches += 1
    print("PATCH E2: CSV append + rotation — OK")
else:
    print("PATCH E2: CSV write — NOT FOUND")

# ── PATCH F: save_to_excel — limit rows ──
# Add row limits after pd.concat for summary and trades
old_excel_summary = "            df_summary = pd.concat([existing_summary, df_summary_new], ignore_index=True)"
new_excel_summary = """            df_summary = pd.concat([existing_summary, df_summary_new], ignore_index=True)
            if len(df_summary) > 2000:
                df_summary = df_summary.tail(2000).reset_index(drop=True)"""

if old_excel_summary in content:
    content = content.replace(old_excel_summary, new_excel_summary, 1)
    patches += 1
    print("PATCH F1: Excel summary row limit — OK")
else:
    print("PATCH F1: Excel summary — NOT FOUND")

old_excel_trades = "                df_trades = pd.concat([existing_trades, df_trades_new], ignore_index=True)"
new_excel_trades = """                df_trades = pd.concat([existing_trades, df_trades_new], ignore_index=True)
                if len(df_trades) > 2000:
                    df_trades = df_trades.tail(2000).reset_index(drop=True)"""

if old_excel_trades in content:
    content = content.replace(old_excel_trades, new_excel_trades, 1)
    patches += 1
    print("PATCH F2: Excel trades row limit — OK")
else:
    print("PATCH F2: Excel trades — NOT FOUND")

# ── PATCH G: save_positions — batch writes ──
old_pos = '''    def save_positions(self):
        """Сохраняет позиции в JSON файл"""
        try:'''
new_pos = '''    def save_positions(self, force=False):
        """Сохраняет позиции в JSON файл (батчинг: пишет раз в 10 вызовов или при force)"""
        if not hasattr(self, '_save_pos_counter'):
            self._save_pos_counter = 0
        self._save_pos_counter += 1
        if not force and self._save_pos_counter % 10 != 0:
            return
        try:'''

if old_pos in content:
    content = content.replace(old_pos, new_pos, 1)
    patches += 1
    print("PATCH G: Batch save_positions — OK")
else:
    print("PATCH G: save_positions — NOT FOUND")

# ── Write result ──
print(f"\nTotal patches applied: {patches}")

with open(SCRIPT, 'w', encoding='utf-8', newline='') as f:
    f.write(content)

print(f"Written {len(content)} bytes")

# Verify syntax
import subprocess
result = subprocess.run(['python3', '-m', 'py_compile', SCRIPT], capture_output=True, text=True)
if result.returncode == 0:
    print("Syntax check: OK ✅")
else:
    print(f"Syntax check: FAILED ❌\n{result.stderr}")
