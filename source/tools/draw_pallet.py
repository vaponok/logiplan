#!/usr/bin/env python3
"""
Иконка «Поддона для материалов», нарисованная заново.

В игре она есть только 100x100, а сам поддон на ней — 25 пикселей в высоту:
нейросети вместо досок рисуют кашу. Поэтому поддон собран из брусков, как
модель в игре — 9 досок сверху вдоль, 5 брусков поперёк, 9 досок снизу, —
спроецирован под ракурс иконки игры и отрисован в её стиле: белый верх,
серые боковины, тёмный контур.

    python tools/draw_pallet.py out.png      (нужны numpy и Pillow)
"""
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 256
SS = 4  # суперсэмплинг: рисуем в 1024 и уменьшаем — гладкие края
LENGTH, WIDTH = 12.0, 8.0
# Оси проекции в пикселях 100-px иконки игры на единицу модели:
EU = np.array([55.0, -14.0]) / 12  # длина: вправо-вверх
EV = np.array([-36.0, -10.0]) / 8  # ширина: влево-вверх
EZ = np.array([0.0, -5.6])  # высота
ORIGIN = np.array([41.0, 60.5])  # передний нижний угол на иконке 100x100

FILL = np.array([[247, 247, 247], [186, 186, 186], [222, 222, 222]], np.float32)  # верх, правая, левая
LINE = np.array([26, 26, 26], np.float32)
LINE_PX = 3  # толщина контура в пикселях суперсэмплинга (нечётная)


def view_dir():
    """Направление взгляда вглубь сцены: EU·a + EV·b − EZ = 0."""
    a, b = np.linalg.solve(np.array([[EU[0], EV[0]], [EU[1], EV[1]]]), EZ)
    v = np.array([a, b, -1.0])
    return v if v[0] > 0 else -v


def spaced(n, total, w):
    gap = (total - n * w) / (n - 1)
    return [(i * (w + gap), i * (w + gap) + w) for i in range(n)]


def pallet_boxes():
    """Бруски (u0, u1, v0, v1, z0, z1): u — длина, v — ширина, z — высота."""
    boxes = [(0, LENGTH, v0, v1, 0, 0.22) for v0, v1 in spaced(9, WIDTH, 0.6)]  # доски снизу
    boxes += [(u0, u1, 0, WIDTH, 0.22, 0.8) for u0, u1 in spaced(5, LENGTH, 1.0)]  # бруски поперёк
    boxes += [(0, LENGTH, v0, v1, 0.8, 1.05) for v0, v1 in spaced(9, WIDTH, 0.6)]  # доски сверху
    return boxes


def draw():
    n = SIZE * SS
    scale = SIZE / 100 * SS
    view = view_dir()

    def screen(p):
        return ORIGIN * scale + scale * (p[0] * EU + p[1] * EV + p[2] * EZ)

    faces = []  # (экранный многоугольник, 3D-вершины, номер заливки)
    for u0, u1, v0, v1, z0, z1 in pallet_boxes():
        for quad, shade in (
            ([(u0, v0, z0), (u1, v0, z0), (u1, v0, z1), (u0, v0, z1)], 1),  # грань к зрителю справа
            ([(u0, v0, z0), (u0, v1, z0), (u0, v1, z1), (u0, v0, z1)], 2),  # грань к зрителю слева
            ([(u0, v0, z1), (u1, v0, z1), (u1, v1, z1), (u0, v1, z1)], 0),  # верх
        ):
            q3 = np.array(quad, float)
            faces.append(([tuple(screen(p)) for p in q3], q3, shade))

    # буфер глубины: у каждого пикселя — ближайшая грань
    ys, xs = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5
    zbuf = np.full((n, n), np.inf, np.float32)
    face_id = np.full((n, n), -1, np.int32)
    for k, (poly, q3, _shade) in enumerate(faces):
        m = Image.new("L", (n, n), 0)
        ImageDraw.Draw(m).polygon(poly, fill=255)
        mask = np.asarray(m) > 0
        a = np.array([[poly[i][0], poly[i][1], 1.0] for i in range(3)])
        b = np.array([q3[i] @ view for i in range(3)])
        try:
            cx, cy, c0 = np.linalg.solve(a, b)  # глубина на грани — аффинная функция x, y
        except np.linalg.LinAlgError:
            continue  # грань видна ребром
        depth = cx * xs + cy * ys + c0
        upd = mask & (depth < zbuf - 1e-4)
        zbuf[upd] = depth[upd]
        face_id[upd] = k

    inside = face_id >= 0
    shades = np.array([f[2] for f in faces])
    rgb = np.zeros((n, n, 3), np.float32)
    rgb[inside] = FILL[shades[face_id[inside]]]
    # контур — там, где меняется грань (и на границе с фоном)
    edge = (face_id != np.roll(face_id, 1, 0)) | (face_id != np.roll(face_id, 1, 1))
    edge = np.asarray(Image.fromarray(edge.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(LINE_PX))) > 0
    rgb[edge] = LINE
    alpha = (inside | edge).astype(np.float32) * 255
    img = Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8), "RGBA")
    return img.resize((SIZE, SIZE), Image.LANCZOS)


if __name__ == "__main__":
    draw().save(sys.argv[1])
