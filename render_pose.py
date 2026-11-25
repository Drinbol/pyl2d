#!/usr/bin/env python3
"""
从 Live2D 模型数据软件渲染默认姿态参考图（无需 OpenGL）。
支持多套皮肤：通过 --texture-dir 指定替换纹理目录。
用法:
    python render_default_pose.py <UV数据JSON> [输出PNG] [选项]
    
示例:
    # 渲染默认姿态
    python render_default_pose.py haru_uv_data.json haru_default_pose.png
    
    # 使用另一套皮肤纹理渲染
    python render_default_pose.py haru_uv_data.json haru_skin2.png --texture-dir ./skins/skin2/
"""
import argparse
import json
import os
import sys
import numpy as np
from PIL import Image
from pathlib import Path
def warp_triangle(src_arr, dst_arr, src_tri, dst_tri, blend=True):
    """
    将 src_arr 中 src_tri 三角形区域的像素，映射到 dst_arr 的 dst_tri 区域。
    使用向量化重心坐标 + 双线性插值。
    blend=False 时直接覆盖写入（用于 PSD 独立图层，避免层内 alpha 混合）。
    """
    src_tri = np.asarray(src_tri, dtype=np.float32)
    dst_tri = np.asarray(dst_tri, dtype=np.float32)
    min_x = max(0, int(np.floor(dst_tri[:, 0].min())))
    max_x = min(dst_arr.shape[1] - 1, int(np.ceil(dst_tri[:, 0].max())))
    min_y = max(0, int(np.floor(dst_tri[:, 1].min())))
    max_y = min(dst_arr.shape[0] - 1, int(np.ceil(dst_tri[:, 1].max())))
    if min_x >= max_x or min_y >= max_y:
        return
    xs = np.arange(min_x, max_x + 1, dtype=np.float32)
    ys = np.arange(min_y, max_y + 1, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)
    pts = np.stack([xv.ravel(), yv.ravel()], axis=1)
    v0 = dst_tri[1] - dst_tri[0]
    v1 = dst_tri[2] - dst_tri[0]
    v2 = pts - dst_tri[0]
    d00 = np.dot(v0, v0)
    d01 = np.dot(v0, v1)
    d11 = np.dot(v1, v1)
    d20 = np.dot(v2, v0)
    d21 = np.dot(v2, v1)
    denom = d00 * d11 - d01 * d01
    if abs(denom) < 1e-10:
        return
    u = (d11 * d20 - d01 * d21) / denom
    v = (d00 * d21 - d01 * d20) / denom
    w = 1.0 - u - v
    mask = (w >= -0.005) & (u >= -0.005) & (v >= -0.005)
    if not np.any(mask):
        return
    src_pts = (
        w[mask][:, None] * src_tri[0] +
        u[mask][:, None] * src_tri[1] +
        v[mask][:, None] * src_tri[2]
    )
    dst_pts = pts[mask].astype(np.int32)
    src_x = np.clip(src_pts[:, 0], 0, src_arr.shape[1] - 1)
    src_y = np.clip(src_pts[:, 1], 0, src_arr.shape[0] - 1)
    x0 = np.floor(src_x).astype(np.int32)
    x1 = np.minimum(x0 + 1, src_arr.shape[1] - 1)
    y0 = np.floor(src_y).astype(np.int32)
    y1 = np.minimum(y0 + 1, src_arr.shape[0] - 1)
    fx = src_x - x0
    fy = src_y - y0
    c00 = src_arr[y0, x0]
    c10 = src_arr[y0, x1]
    c01 = src_arr[y1, x0]
    c11 = src_arr[y1, x1]
    colors = (
        c00 * (1 - fx)[:, None] * (1 - fy)[:, None] +
        c10 * fx[:, None] * (1 - fy)[:, None] +
        c01 * (1 - fx)[:, None] * fy[:, None] +
        c11 * fx[:, None] * fy[:, None]
    )
    # Alpha 混合：后绘制的覆盖先绘制的（参考图不需要复杂混合）
    # 但保留目标像素的 alpha 以支持半透明叠加
    src_colors = np.clip(colors, 0, 255).astype(np.uint8)
    if not blend:
        dst_arr[dst_pts[:, 1], dst_pts[:, 0]] = src_colors
    else:
        dst_alpha = dst_arr[dst_pts[:, 1], dst_pts[:, 0], 3].astype(np.float32) / 255.0
        src_alpha = src_colors[:, 3].astype(np.float32) / 255.0
        out_alpha = src_alpha + dst_alpha * (1 - src_alpha)
        out_alpha_safe = np.where(out_alpha > 0, out_alpha, 1e-6)
        for c in range(3):
            dst_arr[dst_pts[:, 1], dst_pts[:, 0], c] = (
                (src_colors[:, c].astype(np.float32) * src_alpha +
                 dst_arr[dst_pts[:, 1], dst_pts[:, 0], c].astype(np.float32) * dst_alpha * (1 - src_alpha))
                / out_alpha_safe
            ).astype(np.uint8)
        dst_arr[dst_pts[:, 1], dst_pts[:, 0], 3] = (out_alpha * 255).astype(np.uint8)
def resolve_texture_path(original_path, texture_dir=None):
    """如果指定了 texture_dir，尝试在该目录下查找同名纹理。"""
    if texture_dir is None:
        return original_path
    base_name = os.path.basename(original_path)
    alt_path = os.path.join(texture_dir, base_name)
    if os.path.exists(alt_path):
        return alt_path
    return original_path
def crop_to_content(arr):
    """裁剪掉全透明的边缘，返回 (cropped_arr, left, top)。如果全透明返回 (None, 0, 0)。"""
    alpha = arr[:, :, 3]
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)
    if not np.any(rows) or not np.any(cols):
        return None, 0, 0
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    return arr[rmin:rmax + 1, cmin:cmax + 1], int(cmin), int(rmin)
def render_default_pose(json_path, output_path, texture_dir=None, bg_color=None, psd_mode=False):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    model_info = data["model_info"]
    drawables = data["drawables"]
    canvas_pixel_w = int(model_info["canvas_size_pixel"][0])
    canvas_pixel_h = int(model_info["canvas_size_pixel"][1])
    ppu = model_info["pixels_per_unit"]
    textures = model_info["textures"]
    print(f"画布像素尺寸: {canvas_pixel_w}x{canvas_pixel_h}")
    print(f"可绘制对象数量: {len(drawables)}")
    # 加载纹理（支持皮肤替换）
    texture_arrays = {}
    texture_sizes = {}
    for tex_path in textures:
        resolved = resolve_texture_path(tex_path, texture_dir)
        if os.path.exists(resolved):
            img = Image.open(resolved).convert("RGBA")
            print(f"加载纹理: {resolved}")
        else:
            print(f"警告: 纹理不存在，创建空白图: {resolved}")
            img = Image.new("RGBA", (2048, 2048), (0, 0, 0, 0))
        texture_arrays[tex_path] = np.array(img)
        texture_sizes[tex_path] = img.size
    # 按 render_order 排序绘制，并过滤掉不可见的 drawable（opacity < 0.001）
    visible_drawables = [d for d in drawables if d.get("opacity", 1.0) > 0.001]
    sorted_drawables = sorted(visible_drawables, key=lambda d: d.get("render_order", d["index"]))
    print(f"可见 drawable 数量: {len(sorted_drawables)} / {len(drawables)}")
    if psd_mode:
        # PSD 模式：每个 drawable 渲染为独立图层
        layers = []  # [(name, pil_img, left, top), ...]
        for d_idx, d in enumerate(sorted_drawables):
            tex_file = d["texture_file"]
            if tex_file not in texture_arrays:
                continue
            tex_w, tex_h = texture_sizes[tex_file]
            tex_arr = texture_arrays[tex_file]
            verts = d["vertices"]
            skin_pixels = []
            for vx, vy in verts:
                px = vx * ppu + canvas_pixel_w / 2.0
                py = canvas_pixel_h / 2.0 - vy * ppu
                skin_pixels.append((px, py))
            uvs = d["uvs"]
            tex_pixels = []
            for u, v in uvs:
                tx = u * tex_w
                ty = v * tex_h
                tex_pixels.append((tx, ty))
            layer_canvas = np.zeros((canvas_pixel_h, canvas_pixel_w, 4), dtype=np.uint8)
            indices = d["indices"]
            for i in range(len(indices) // 3):
                i0 = indices[i * 3]
                i1 = indices[i * 3 + 1]
                i2 = indices[i * 3 + 2]
                src_tri = [tex_pixels[i0], tex_pixels[i1], tex_pixels[i2]]
                dst_tri = [skin_pixels[i0], skin_pixels[i1], skin_pixels[i2]]
                warp_triangle(tex_arr, layer_canvas, src_tri, dst_tri, blend=False)
            cropped, left, top = crop_to_content(layer_canvas)
            if cropped is not None:
                layer_name = f"{d['index']}:{d['id']}"
                layers.append((layer_name, Image.fromarray(cropped), left, top))
            if (d_idx + 1) % 10 == 0 or d_idx == len(sorted_drawables) - 1:
                print(f"  已渲染 {d_idx + 1}/{len(sorted_drawables)} 个 drawable 图层")
        # 写入 PSD
        from psd_tools import PSDImage
        from psd_tools.api.layers import PixelLayer
        from psd_tools.constants import Compression
        psd = PSDImage.new(mode='RGBA', size=(canvas_pixel_w, canvas_pixel_h))
        # 按 render_order 从小到大追加：先追加的在下层，后追加的在上层
        for name, pil_img, left, top in layers:
            layer = PixelLayer.frompil(
                image=pil_img,
                parent=psd,
                name=name,
                top=top,
                left=left,
                compression=Compression.RLE
            )
            psd.append(layer)
        psd.save(output_path)
        print(f"已保存分层 PSD: {output_path}，共 {len(layers)} 个图层")
        return output_path
    else:
        # PNG 模式：混合到单一画布
        if bg_color is None:
            canvas = np.zeros((canvas_pixel_h, canvas_pixel_w, 4), dtype=np.uint8)
        else:
            canvas = np.full((canvas_pixel_h, canvas_pixel_w, 4), bg_color, dtype=np.uint8)
        for d_idx, d in enumerate(sorted_drawables):
            tex_file = d["texture_file"]
            if tex_file not in texture_arrays:
                continue
            tex_w, tex_h = texture_sizes[tex_file]
            tex_arr = texture_arrays[tex_file]
            verts = d["vertices"]
            skin_pixels = []
            for vx, vy in verts:
                px = vx * ppu + canvas_pixel_w / 2.0
                py = canvas_pixel_h / 2.0 - vy * ppu
                skin_pixels.append((px, py))
            uvs = d["uvs"]
            tex_pixels = []
            for u, v in uvs:
                tx = u * tex_w
                ty = v * tex_h
                tex_pixels.append((tx, ty))
            indices = d["indices"]
            for i in range(len(indices) // 3):
                i0 = indices[i * 3]
                i1 = indices[i * 3 + 1]
                i2 = indices[i * 3 + 2]
                src_tri = [tex_pixels[i0], tex_pixels[i1], tex_pixels[i2]]
                dst_tri = [skin_pixels[i0], skin_pixels[i1], skin_pixels[i2]]
                warp_triangle(tex_arr, canvas, src_tri, dst_tri, blend=True)
            if (d_idx + 1) % 10 == 0 or d_idx == len(drawables) - 1:
                print(f"  已绘制 {d_idx + 1}/{len(drawables)} 个 drawable")
        result = Image.fromarray(canvas)
        result.save(output_path)
        print(f"已保存参考图: {output_path}")
        return output_path
def main():
    parser = argparse.ArgumentParser(
        description="从 Live2D 模型数据软件渲染默认姿态参考图"
    )
    parser.add_argument("json", help="UV 数据 JSON 文件路径")
    parser.add_argument("output", nargs="?", default="default_pose.png", help="输出 PNG 路径")
    parser.add_argument("--texture-dir", default=None, help="替换纹理目录（用于多套皮肤）")
    parser.add_argument("--batch", action="store_true",
                        help="批量模式：texture-dir 下的每个子目录视为一套皮肤，全部生成")
    parser.add_argument("--bg", nargs=4, type=int, default=None,
                        metavar=("R", "G", "B", "A"),
                        help="背景颜色，例如 --bg 255 255 255 255")
    parser.add_argument("--psd", action="store_true",
                        help="输出为分层 PSD 文件，每个可见 drawable 一个独立图层（需在 Photoshop 中打开）")
    args = parser.parse_args()
    if not os.path.exists(args.json):
        print(f"错误: JSON 文件不存在: {args.json}")
        sys.exit(1)
    bg = tuple(args.bg) if args.bg else None
    # 自动根据 --psd 和输出后缀判断模式
    psd_mode = args.psd
    if not psd_mode and args.output.lower().endswith('.psd'):
        psd_mode = True
    try:
        if args.batch and args.texture_dir:
            skin_dirs = [d for d in Path(args.texture_dir).iterdir() if d.is_dir()]
            if not skin_dirs:
                print(f"警告: {args.texture_dir} 下没有找到子目录，按单套皮肤处理")
                render_default_pose(args.json, args.output, args.texture_dir, bg, psd_mode=psd_mode)
            else:
                base_output = Path(args.output)
                for skin_dir in sorted(skin_dirs):
                    skin_name = skin_dir.name
                    suffix = '.psd' if psd_mode else base_output.suffix
                    out_path = str(base_output.parent / f"{base_output.stem}_{skin_name}{suffix}")
                    print(f"\n===== 生成皮肤: {skin_name} =====")
                    render_default_pose(args.json, out_path, str(skin_dir), bg, psd_mode=psd_mode)
        else:
            render_default_pose(args.json, args.output, args.texture_dir, bg, psd_mode=psd_mode)
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
if __name__ == "__main__":
    main()