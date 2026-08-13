"""
mask_shapes.py
ワードクラウド用のマスク形状（円・正方形・長方形・横長楕円・ひし形）をnumpy配列で生成する。
輪郭にランダムな丸みの凹凸（雲のような膨らみ）を重ねて、幾何学的に厳密すぎない
やわらかい輪郭にする。wordcloudライブラリの慣例に合わせ、白(255)が除外領域、黒(0)が描画可能領域。
"""

import math
import random

import numpy as np
from PIL import Image, ImageDraw

MASK_SHAPES = ['円', '正方形', '長方形', '横長楕円', 'ひし形']


def generate_mask(shape: str, size: int = 800, cloud_bumps: bool = True) -> np.ndarray:
    """指定した形状のマスク配列を返す（size×sizeの正方形キャンバス内に形状を配置）"""
    img = Image.new('L', (size, size), color=255)
    draw = ImageDraw.Draw(img)
    margin = int(size * 0.08)
    box = (margin, margin, size - margin, size - margin)

    if shape == '円':
        draw.ellipse(box, fill=0)
    elif shape == '正方形':
        draw.rectangle(box, fill=0)
    elif shape == '長方形':
        h_margin = int(size * 0.22)
        box = (margin, h_margin, size - margin, size - h_margin)
        draw.rectangle(box, fill=0)
    elif shape == '横長楕円':
        h_margin = int(size * 0.2)
        box = (margin, h_margin, size - margin, size - h_margin)
        draw.ellipse(box, fill=0)
    elif shape == 'ひし形':
        cx, cy = size // 2, size // 2
        r = size // 2 - margin
        draw.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=0)
    else:
        raise ValueError(f'未対応の形状: {shape}')

    if cloud_bumps:
        _add_cloud_bumps(img, box)

    return np.array(img)


def _add_cloud_bumps(img: Image.Image, box: tuple, n_bumps: int = 16, seed: int = 42) -> None:
    """輪郭に沿ってランダムな円を重ね描きし、雲のような丸い凹凸のある輪郭にする"""
    rng = random.Random(seed)
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2

    for i in range(n_bumps):
        angle = 2 * math.pi * i / n_bumps + rng.uniform(-0.2, 0.2)
        bump_r = rng.uniform(0.14, 0.24) * min(rx, ry)
        bx = cx + math.cos(angle) * rx * rng.uniform(0.88, 1.02)
        by = cy + math.sin(angle) * ry * rng.uniform(0.88, 1.02)
        draw.ellipse((bx - bump_r, by - bump_r, bx + bump_r, by + bump_r), fill=0)
