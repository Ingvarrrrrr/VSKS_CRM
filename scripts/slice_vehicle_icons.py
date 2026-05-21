"""Нарезка иконок ТС из image3.jpeg — 1024×416 px, 4 ряда × 8 столбцов = 32 ячейки.
Силуэты подписаны (нижняя 1/3 ячейки), верхние 2/3 содержат сам силуэт + текстовый лейбл.
Используем tight bbox + ручной crop текста подписи."""
from PIL import Image
import pathlib

SRC = pathlib.Path(__file__).parent.parent / '.tmp_docx_media' / 'image3.jpeg'
DST = pathlib.Path(__file__).parent.parent / 'frontend' / 'public' / 'vehicle-icons'
DST.mkdir(parents=True, exist_ok=True)

im = Image.open(SRC).convert('RGBA')
W, H = im.size  # 1024×416
COLS, ROWS = 8, 4
CELL_W, CELL_H = W // COLS, H // ROWS  # 128, 104

# Mapping: Vehicle.type → (row, col) в image3 (силуэт без подписи)
# Берём силуэты которые лучше всего matchat реальный fleet:
MAP = {
    'car_light':    (0, 4),   # SEDAN
    'suv':          (2, 2),   # SUV — ТИП «Внедорожник»
    'pickup':       (2, 3),   # PICKUP TRUCK
    'minivan':      (2, 7),   # MINIVAN
    'truck_van':    (3, 5),   # CARGO VAN (закрытый фургон)
    'truck_board':  (3, 4),   # CAB CHASSIS VAN (грузовик с открытой платформой)
    'bus':          (3, 6),   # PASSENGER VAN
    'other':        (0, 4),   # fallback SEDAN
    # truck_metal — нет точного силуэта, используем CAB CHASSIS VAN
    'truck_metal':  (3, 4),
}

# Координаты подписи (нижняя часть ячейки) — обрезаем чтобы убрать текст:
# Силуэт занимает примерно top 70% ячейки, подпись — bottom 30%
SILHOUETTE_HEIGHT_RATIO = 0.70  # crop'аем верхние 70%

# Threshold — пиксели темнее этого считаем «силуэтом»:
DARK_THRESHOLD = 100


def tight_crop(crop_img):
    """Найти tight bbox силуэта по тёмным пикселям, отбросив подпись и пустоты."""
    w, h = crop_img.size
    # Сначала обрежем низ — отбросим зону подписи
    crop_no_label = crop_img.crop((0, 0, w, int(h * SILHOUETTE_HEIGHT_RATIO)))
    gray_top = crop_no_label.convert('L')
    # Найти tight bbox по тёмным пикселям
    mask = gray_top.point(lambda p: 255 if p < DARK_THRESHOLD else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return crop_img  # fallback
    # Добавим небольшой padding 2px вокруг
    pad = 2
    bbox = (
        max(0, bbox[0] - pad),
        max(0, bbox[1] - pad),
        min(crop_no_label.size[0], bbox[2] + pad),
        min(crop_no_label.size[1], bbox[3] + pad),
    )
    tight = crop_no_label.crop(bbox)
    # Сделать прозрачный фон: белые пиксели → alpha=0
    tight = tight.convert('RGBA')
    pixels = tight.load()
    for y in range(tight.size[1]):
        for x in range(tight.size[0]):
            r, g, b, a = pixels[x, y]
            # Серый/белый фон → прозрачный. Тёмные пиксели → чёрный.
            if r > 220 and g > 220 and b > 220:
                pixels[x, y] = (0, 0, 0, 0)
            elif r < DARK_THRESHOLD and g < DARK_THRESHOLD and b < DARK_THRESHOLD:
                pixels[x, y] = (0, 0, 0, 255)  # чёрный силуэт
            else:
                # Грязные пиксели на границе — оставляем как есть, но усиливаем
                pixels[x, y] = (0, 0, 0, a)
    return tight


# Удаляем старые PNG чтобы не накапливать мусор:
for old in DST.glob('*.png'):
    old.unlink()

for typ, (row, col) in MAP.items():
    x = col * CELL_W
    y = row * CELL_H
    cell = im.crop((x, y, x + CELL_W, y + CELL_H))
    tight = tight_crop(cell)
    out = DST / f'{typ}.png'
    tight.save(out, optimize=True)
    print(f'  -> {typ}.png ({tight.size[0]}x{tight.size[1]})')

print(f'Done: {len(list(DST.glob("*.png")))} PNG in {DST}')
