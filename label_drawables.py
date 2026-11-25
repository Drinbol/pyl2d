#!/usr/bin/env python3
"""
在参考图上标注每个可见 drawable 的 index 和 id，用于诊断部件对应关系。

用法:
    python label_drawables.py <UV数据JSON> <输出PNG>

示例:
    python label_drawables.py work/boy_default.json boy_default_labeled.png
"""
import json
import os
import sys
from PIL import Image, ImageDraw


def label_reference(json_path, output_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    canvas_w = int(data["model_info"]["canvas_size_pixel"][0])
    canvas_h = int(data["model_info"]["canvas_size_pixel"][1])
    ppu = data["model_info"]["pixels_per_unit"]
    drawables = data["drawables"]

    # 用原纹理作为背景（可选）
    textures = data["model_info"]["textures"]
    if textures and os.path.exists(textures[0]):
        bg = Image.open(textures[0]).convert("RGBA")
        bg = bg.resize((canvas_w, canvas_h), Image.Resampling.LANCZOS)
    else:
        bg = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))

    img = bg.copy()
    draw = ImageDraw.Draw(img)

    # 只标注可见的 drawable
    visible = [d for d in drawables if d.get("opacity", 1.0) > 0]
    print(f"标注 {len(visible)} 个可见 drawable")

    for d in visible:
        verts = d["vertices"]
        if not verts:
            continue

        # 计算屏幕像素坐标和包围盒中心
        xs = [v[0] * ppu + canvas_w / 2.0 for v in verts]
        ys = [canvas_h / 2.0 - v[1] * ppu for v in verts]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)

        idx = d["index"]
        did = d["id"]

        # 画红色圆点
        r = 6
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 0, 0, 255), outline=(0, 0, 0, 255), width=1)

        # 标注文字：index + 截断的 id
        text = f"{idx}:{did[:12]}"
        # 简单避免文字重叠：根据 index 奇偶微调位置
        tx = cx + 10
        ty = cy - 10
        if idx % 2 == 1:
            ty += 20

        # 黑色描边背景提高可读性
        for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            draw.text((tx + dx, ty + dy), text, fill=(0, 0, 0, 255))
        draw.text((tx, ty), text, fill=(255, 255, 0, 255))

    img.save(output_path)
    print(f"已保存标注图: {output_path}")


def main():
    if len(sys.argv) < 3:
        print("用法: python label_drawables.py <UV数据JSON> <输出PNG>")
        print("示例: python label_drawables.py work/boy_default.json boy_labeled.png")
        sys.exit(1)

    label_reference(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
