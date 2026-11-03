#!/usr/bin/env python3
"""v7 智能裁切脚本：自适应背景检测 → 安全裁量 → 裁后验证

SOP §8.4.5 算法实现。
用法: python3 crop_illustration_v7.py <input.png> [output.png] [--check]
"""

import sys
import os
from PIL import Image
import numpy as np

# 裁切常量（SOP §8.4.5）
CROP_L = 62        # 左裁
CROP_R = 62        # 右裁
CROP_B = 140       # 底裁（水印带：ImageGen "图片由AI生成" 水印高度实测约 50-90px，取 140px 兜底）
MARGIN_MIN = 0.03  # 裁后最小边距比（≥3% ✅）
WATERMARK_BAND = 140


def detect_background_color(img: Image.Image) -> tuple:
    """自适应背景色检测：取四角 20×20 区域中位数"""
    w, h = img.size
    corners = [
        img.crop((0, 0, 20, 20)),
        img.crop((w - 20, 0, w, 20)),
        img.crop((0, h - 20, 20, h)),
        img.crop((w - 20, h - 20, w, h)),
    ]
    pixels = []
    for c in corners:
        arr = np.array(c)
        pixels.extend(arr.reshape(-1, 3))
    pixels = np.array(pixels)
    median = np.median(pixels, axis=0).astype(int)
    return tuple(median)


def find_content_bbox(img: Image.Image, bg_color: tuple, tolerance: int = 18) -> tuple:
    """定位非背景像素 bbox = (L, T, R, B)"""
    arr = np.array(img)
    diff = np.abs(arr.astype(int) - np.array(bg_color, dtype=int))
    is_content = np.any(diff > tolerance, axis=2)
    rows = np.any(is_content, axis=1)
    cols = np.any(is_content, axis=0)
    if not rows.any():
        return None
    row_idx = np.where(rows)[0]
    col_idx = np.where(cols)[0]
    return (col_idx[0], row_idx[0], col_idx[-1] + 1, row_idx[-1] + 1)


def calc_safe_crop(img: Image.Image, bbox: tuple) -> tuple:
    """计算安全裁量（L/R/B），返回 (crop_L, crop_R, crop_B)

    铁律：宁可少裁/不裁，绝不切到内容；但底部水印带必须无条件去除。
    ImageGen 的 "图片由AI生成" 水印位于右下角，灰字在 cream 背景上对比度低，
    bbox 检测会漏检，因此底部必须强制裁 WATERMARK_BAND px。
    """
    w, h = img.size
    bbox_L, bbox_T, bbox_R, bbox_B = bbox

    # 内容距边
    left_margin = bbox_L
    right_margin = w - bbox_R
    bottom_margin = h - bbox_B

    # 3% buffer（内容须保留的安全余量）
    buffer_3pct = int(w * MARGIN_MIN)

    def safe_side(margin_px, target_px):
        """单边裁量：只能裁内容以外的纯背景，保留 ≥3% buffer"""
        available = max(0, margin_px - buffer_3pct)
        return min(target_px, available)

    safe_L = safe_side(left_margin, CROP_L)
    safe_R = safe_side(right_margin, CROP_R)

    # 底部：强制裁水印带。WATERMARK_BAND=140px 已覆盖实测水印高度（50-90px）+ 安全余量。
    if bottom_margin >= WATERMARK_BAND + 5:
        safe_B = WATERMARK_BAND  # 余量充足，完整裁掉水印带
    elif bottom_margin >= 10:
        safe_B = bottom_margin - 5  # 余量不足，退到内容前 5px；水印可能残留，需人工确认
        print(f"⚠️ 底部余量仅 {bottom_margin}px < {WATERMARK_BAND + 5}px，水印可能未完全去除")
    else:
        safe_B = 0  # 内容贴底，无法裁
        print("⚠️ 内容贴底，无法裁切水印带，建议重生成 prompt 并加大底部留白")

    return (safe_L, safe_R, safe_B)


def verify_crop(img_cropped: Image.Image, bg_color: tuple, tolerance: int = 18) -> dict:
    """裁后验证：检查四边实际边距比"""
    w, h = img_cropped.size
    bbox = find_content_bbox(img_cropped, bg_color, tolerance)
    if bbox is None:
        return {"status": "fail", "reason": "no content found"}

    bbox_L, bbox_T, bbox_R, bbox_B = bbox
    margins = {
        "L": bbox_L / w,
        "R": (w - bbox_R) / w,
        "T": bbox_T / h,
        "B": (h - bbox_B) / h,
    }
    min_margin = min(margins.values())
    min_side = min(margins, key=margins.get)

    if [v for v in margins.values() if v < 0.02]:
        status = "fail"
        reason = f"{min_side}={min_margin:.1%} < 2% 贴边"
    elif [v for v in margins.values() if v < 0.03]:
        status = "warn"
        reason = f"{min_side}={min_margin:.1%} in [2%,3%) 人工确认"
    else:
        status = "ok"
        reason = f"min={min_margin:.1%} @{min_side}"

    return {"status": status, "reason": reason, "margins": margins}


def pad_image(img: Image.Image, padding: int = 80) -> Image.Image:
    """给图像加纯色边框（程控留白，兜底 ImageGen 不遵守 prompt 留白指令）"""
    bg = detect_background_color(img)
    w, h = img.size
    new_w, new_h = w + 2 * padding, h + 2 * padding
    padded = Image.new("RGB", (new_w, new_h), bg)
    padded.paste(img, (padding, padding))
    return padded


def crop_image(input_path: str, output_path: str = None, check_only: bool = False, pad: int = 0):
    """主流程

    Args:
        pad: 生成前加多少 px 纯色边框（仅当 ImageGen 完全不留白时使用，手绘风默认 0）
    """
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_cropped{ext}"

    img = Image.open(input_path).convert("RGB")
    w, h = img.size
    print(f"原始: {w}×{h}")

    # 0. 可选：加边框（仅 ImageGen 电影感图/内容贴边时使用；手绘科普风默认不加）
    if pad > 0:
        print(f"→ 加 {pad}px 程控边框...")
        img = pad_image(img, padding=pad)
        w, h = img.size
        print(f"加边后: {w}×{h}")

    # 1. 自适应背景色检测
    bg = detect_background_color(img)
    print(f"背景色(RGB): {bg}")

    # 2. 定位内容 bbox
    bbox = find_content_bbox(img, bg)
    if bbox is None:
        print("⚠️ 未检测到内容，跳过裁切")
        return
    print(f"内容 bbox: L={bbox[0]} T={bbox[1]} R={bbox[2]} B={bbox[3]}")

    # 3. 安全裁量
    crop_L, crop_R, crop_B = calc_safe_crop(img, bbox)
    print(f"安全裁量: L={crop_L} R={crop_R} B={crop_B} (T=0)")

    if check_only:
        new_w = w - crop_L - crop_R
        new_h = h - crop_B
        print(f"裁后尺寸: {new_w}×{new_h}")
        if crop_L + crop_R < w and crop_B < h:
            cropped = img.crop((crop_L, 0, w - crop_R, h - crop_B))
            result = verify_crop(cropped, bg)
            print(f"裁后验证: {result['status'].upper()} - {result['reason']}")
            if result["status"] != "ok":
                print(f"  边距: {result['margins']}")
        return

    # 4. 执行裁切
    cropped = img.crop((crop_L, 0, w - crop_R, h - crop_B))
    print(f"裁后尺寸: {cropped.size[0]}×{cropped.size[1]}")

    # 5. 裁后验证
    result = verify_crop(cropped, bg)
    print(f"裁后验证: {result['status'].upper()} - {result['reason']}")
    if result["status"] != "ok":
        print(f"  边距: {result['margins']}")

    # 保存
    cropped.save(output_path, "PNG")
    print(f"✅ 保存: {output_path} ({os.path.getsize(output_path)/1024:.0f}KB)")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 crop_illustration_v7.py <input.png> [output.png] [--check] [--pad N]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    check_only = "--check" in sys.argv
    pad = 0
    if "--pad" in sys.argv:
        try:
            pad = int(sys.argv[sys.argv.index("--pad") + 1])
        except (ValueError, IndexError):
            print("❌ --pad 后需跟整数像素值")
            sys.exit(1)

    # 输出路径是 --check 的修正
    if output_path == "--check":
        output_path = None

    if not os.path.exists(input_path):
        print(f"❌ 文件不存在: {input_path}")
        sys.exit(1)

    crop_image(input_path, output_path, check_only, pad=pad)
