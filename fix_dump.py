#!/usr/bin/env python3
"""
Fix SQL dump to match production schema.
Reads the dump, gets production column info via SSH,
rewrites INSERTs to only include columns that exist in production.
"""
import sys
import os
import re
import paramiko

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOST = os.environ.get("REMOTE_HOST", "201.34.139.168")
USER = "root"
PASSWORD = os.environ.get("REMOTE_PASS")
if not PASSWORD:
    print("Задай REMOTE_PASS в окружении", file=sys.stderr)
    sys.exit(1)

def ssh_run(cmd, timeout=30):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASSWORD, timeout=10)
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    client.close()
    return out

def get_production_columns():
    """Get all table->columns mapping from production DB."""
    out = ssh_run(
        'docker exec vsks-crm-db-1 psql -U vsks -d vsks_crm -t -c "'
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema='public' ORDER BY table_name, ordinal_position;"
        '"'
    )
    schema = {}
    for line in out.strip().split('\n'):
        if '|' not in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 2:
            table, col = parts[0], parts[1]
            if table not in schema:
                schema[table] = set()
            schema[table].add(col)
    return schema

def parse_insert(line):
    """Parse INSERT INTO public.table (col1, col2, ...) VALUES (val1, val2, ...);"""
    m = re.match(r"INSERT INTO public\.(\w+)\s+\(([^)]+)\)\s+VALUES\s+\((.+)\);$", line)
    if not m:
        return None
    table = m.group(1)
    cols = [c.strip() for c in m.group(2).split(',')]
    # Parse values carefully (handling strings with commas)
    values_str = m.group(3)
    values = parse_values(values_str)
    return table, cols, values

def parse_values(s):
    """Parse SQL values list, handling quoted strings with commas and parentheses."""
    values = []
    current = []
    in_quote = False
    depth = 0
    i = 0
    while i < len(s):
        ch = s[i]
        if in_quote:
            current.append(ch)
            if ch == "'" and i + 1 < len(s) and s[i+1] == "'":
                current.append("'")
                i += 2
                continue
            elif ch == "'":
                in_quote = False
        else:
            if ch == "'":
                in_quote = True
                current.append(ch)
            elif ch == '(' :
                depth += 1
                current.append(ch)
            elif ch == ')':
                depth -= 1
                current.append(ch)
            elif ch == ',' and depth == 0:
                values.append(''.join(current).strip())
                current = []
                i += 1
                continue
            else:
                current.append(ch)
        i += 1
    if current:
        values.append(''.join(current).strip())
    return values

PG_RESERVED = {'position', 'order', 'user', 'table', 'column', 'group', 'select', 'where', 'from', 'limit', 'offset'}

def rebuild_insert(table, cols, values, valid_cols):
    """Rebuild INSERT statement with only valid columns."""
    pairs = [(c, v) for c, v in zip(cols, values) if c in valid_cols]
    if not pairs:
        return None
    new_cols = []
    for c, _ in pairs:
        if c.lower() in PG_RESERVED:
            new_cols.append(f'"{c}"')
        else:
            new_cols.append(c)
    new_vals = [p[1] for p in pairs]
    return f"INSERT INTO public.{table} ({', '.join(new_cols)}) VALUES ({', '.join(new_vals)});"

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/vsks_data_clean.sql"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "/tmp/vsks_data_fixed.sql"

    print("Getting production schema...")
    schema = get_production_columns()
    print(f"Got schema for {len(schema)} tables")
    for t, cols in sorted(schema.items()):
        print(f"  {t}: {len(cols)} columns")

    print(f"\nProcessing {input_file}...")

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    output_lines = []
    stats = {'total': 0, 'modified': 0, 'skipped_table': 0, 'skipped_roles': 0, 'kept': 0}
    dropped_cols = {}

    for line in lines:
        stripped = line.strip()

        # Skip roles-related
        if 'public.roles' in stripped:
            stats['skipped_roles'] += 1
            continue

        # Not an INSERT — keep as-is
        if not stripped.startswith('INSERT INTO public.'):
            output_lines.append(line)
            continue

        stats['total'] += 1
        parsed = parse_insert(stripped)

        if not parsed:
            # Can't parse — keep as-is
            output_lines.append(line)
            stats['kept'] += 1
            continue

        table, cols, values = parsed
        # Strip double quotes from column names (e.g. "position" -> position)
        cols = [c.strip('"') for c in cols]

        if table not in schema:
            stats['skipped_table'] += 1
            print(f"  WARNING: table '{table}' not in production — skipping")
            continue

        valid_cols = schema[table]
        removed = [c for c in cols if c not in valid_cols]

        if removed:
            if table not in dropped_cols:
                dropped_cols[table] = set()
            dropped_cols[table].update(removed)
            stats['modified'] += 1

        if len(cols) != len(values):
            print(f"  WARNING: column/value count mismatch in {table}: {len(cols)} cols, {len(values)} vals — skipping")
            continue

        new_insert = rebuild_insert(table, cols, values, valid_cols)
        if new_insert:
            output_lines.append(new_insert + '\n')
        else:
            stats['skipped_table'] += 1

    # Write output
    with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
        f.writelines(output_lines)

    print(f"\nDone!")
    print(f"  Total INSERTs processed: {stats['total']}")
    print(f"  Modified (columns stripped): {stats['modified']}")
    print(f"  Skipped (table not in prod): {stats['skipped_table']}")
    print(f"  Skipped (roles): {stats['skipped_roles']}")
    print(f"  Output: {output_file} ({len(output_lines)} lines)")

    if dropped_cols:
        print(f"\nDropped columns per table:")
        for t, cols in sorted(dropped_cols.items()):
            print(f"  {t}: {sorted(cols)}")

if __name__ == "__main__":
    main()
