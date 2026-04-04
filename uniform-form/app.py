"""Minimal backend for uniform clothing order form."""
import json
import csv
import os
from datetime import datetime
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()

DATA_DIR = "/app/data"
CSV_FILE = os.path.join(DATA_DIR, "orders.csv")
JSON_FILE = os.path.join(DATA_DIR, "orders.json")

os.makedirs(DATA_DIR, exist_ok=True)


class Row(BaseModel):
    region: str
    item: str
    size: str
    height: str
    qty: str
    fio: str
    address: str = ""
    phone: str


class Submission(BaseModel):
    rows: list[Row]


def next_id():
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return len(data) + 1
    return 1


@app.post("/uniform-api/submit")
async def submit(sub: Submission):
    order_id = next_id()
    ts = datetime.now().isoformat(timespec="seconds")

    entry = {
        "id": order_id,
        "timestamp": ts,
        "rows": [r.model_dump() for r in sub.rows],
    }
    orders = []
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            orders = json.load(f)
    orders.append(entry)
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

    write_header = not os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        if write_header:
            w.writerow(["ID", "Дата", "Регион", "Наименование", "Размер", "Рост",
                         "Количество", "Фамилия", "Имя", "Отчество", "Адрес пункта выдачи СДЭК", "Телефон"])
        for r in sub.rows:
            w.writerow([order_id, ts, r.region, r.item, r.size, r.height,
                         r.qty, r.fio, r.address, r.phone])

    return {"id": order_id, "status": "ok"}


@app.get("/uniform-api/orders")
async def get_orders():
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


@app.get("/uniform-api/export")
async def export_csv():
    if os.path.exists(CSV_FILE):
        return FileResponse(CSV_FILE, filename="orders.csv", media_type="text/csv")
    return {"error": "No data yet"}


app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")
