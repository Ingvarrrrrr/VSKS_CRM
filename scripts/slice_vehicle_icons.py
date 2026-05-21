"""Нарезка эталонной картинки силуэтов на 14 PNG для VehicleTypeIcon."""
from PIL import Image
import os
import pathlib

SRC = pathlib.Path(__file__).parent.parent / '.tmp_docx_media' / 'image2.png'
DST = pathlib.Path(__file__).parent.parent / 'frontend' / 'public' / 'vehicle-icons'
DST.mkdir(parents=True, exist_ok=True)

im = Image.open(SRC).convert('RGBA')
W, H = im.size  # 600x306
print(f'src: {W}x{H}')

# Координаты выбранных силуэтов (приблизительная сетка 6 cols × 7 rows = 100x44 каждая ячейка).
# Подбери индексы (row, col) с учётом визуального содержимого:
# row 0: sedan series (1 буква + 3 цифры седан)
# row 1: SUV/crossover series
# row 2: SUV taller/hatchback variants
# row 3: pickup + larger SUVs
# row 4: cargo vans + flatbed truck
# row 5: pickup truck + passenger vans
# row 6: cargo trucks + box truck + tank truck

CELL_W = W // 6
CELL_H = H // 7

# Mapping: vehicle_type → (row, col) в сетке (нумерация с 0)
# Для типов которых нет в коллаже — None (fallback на MDI в Vue компоненте)
MAP = {
    'car_light':    (0, 3),   # классический седан
    'minivan':      (4, 0),   # высокий минивэн
    'truck_van':    (5, 1),   # cargo van
    'truck_board':  (4, 4),   # flatbed truck с открытым кузовом
    'truck_metal':  (6, 5),   # длинный грузовик с прицепом
    'truck_tank':   None,     # нет в коллаже, fallback
    'bus':          (5, 4),   # пассажирский фургон / minibus
    'special':      None,     # нет, fallback
    'quadbike':     None,
    'snowmobile':   None,
    'boat':         None,
    'boat_motor':   None,
    'trailer':      None,
    'other':        (0, 0),   # generic sedan
}

# Crop + save
for typ, coord in MAP.items():
    if coord is None:
        continue
    row, col = coord
    x = col * CELL_W
    y = row * CELL_H
    crop = im.crop((x, y, x + CELL_W, y + CELL_H))
    # Trim whitespace вокруг силуэта — оставить только bounding box
    bbox = crop.getbbox()
    if bbox:
        crop = crop.crop(bbox)
    out = DST / f'{typ}.png'
    crop.save(out, optimize=True)
    print(f'  -> {typ}.png ({crop.size[0]}x{crop.size[1]})')

print(f'\nDone: {len([v for v in MAP.values() if v])} icons in {DST}')
