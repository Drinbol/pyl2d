#!/usr/bin/env python3
"""
将重绘好的完整角色图（静态PNG）反向映射回 Live2D 纹理。
支持遮罩：只替换遮罩圈选的区域，其余保持原纹理不变。

用法:
    python remap_skin_to_texture.py <模型UV数据JSON> <新皮肤PNG> [输出目录] [选项]
    
示例:
    # 全图映射
    python remap_skin_to_texture.py haru_uv_data.json new_skin.png remapped_textures
    
    # 只映射遮罩区域（白色=修改，黑色=保留）
    python remap_skin_to_texture.py haru_uv_data.json new_skin.png remapped_textures --mask edit_mask.png

    # 遮罩 + 排除指定部件（粗略画遮罩后手动排除不需要的部件）
    python remap_skin_to_texture.py haru_uv_data.json new_skin.png remapped_textures --mask edit_mask.png --exclude-drawables ArtMesh52,ArtMesh54

说明:
    1. 先运行 extract_uv_data.py 生成 JSON 数据
    2. 准备一张与模型默认姿态对齐的完整重绘图（PNG）
    3. （可选）准备一张同尺寸的遮罩图，白色表示"此区域已修改"，黑色表示"保持原样"
    4. 运行此脚本生成新的纹理文件，直接替换原模型纹理即可
"""
import argparse
import json
import os
import sys
import numpy as np
from PIL import Image
from pathlib import Path


def warp_triangle(src_arr, dst_arr, src_tri, dst_tri, mask_arr=None, mask_threshold=128):
    """
    将 src_arr 中 src_tri 三角形区域的像素，通过仿射映射写入 dst_arr 的 dst_tri 区域。
    如果提供了 mask_arr，只写入遮罩值为白色（>=阈值）的对应源像素。
    """
    src_tri = np.asarray(src_tri, dtype=np.float32)
    dst_tri = np.asarray(dst_tri, dtype=np.float32)

    # 目标三角形的像素包围盒
    min_x = max(0, int(np.floor(dst_tri[:, 0].min())))
    max_x = min(dst_arr.shape[1] - 1, int(np.ceil(dst_tri[:, 0].max())))
    min_y = max(0, int(np.floor(dst_tri[:, 1].min())))
    max_y = min(dst_arr.shape[0] - 1, int(np.ceil(dst_tri[:, 1].max())))

    if min_x >= max_x or min_y >= max_y:
        return

    # 生成包围盒内所有像素坐标
    xs = np.arange(min_x, max_x + 1, dtype=np.float32)
    ys = np.arange(min_y, max_y + 1, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)
    pts = np.stack([xv.ravel(), yv.ravel()], axis=1)  # (N, 2)

    # ---- 计算重心坐标 (w, u, v) 相对于 dst_tri ----
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
        return  # 退化三角形

    u = (d11 * d20 - d01 * d21) / denom
    v = (d00 * d21 - d01 * d20) / denom
    w = 1.0 - u - v

    # 微小负容差：消除相邻三角形之间的缝隙
    tri_mask = (w >= -0.005) & (u >= -0.005) & (v >= -0.005)
    if not np.any(tri_mask):
        return

    # 用同样的重心坐标在源三角形中插值
    src_pts = (
        w[tri_mask][:, None] * src_tri[0] +
        u[tri_mask][:, None] * src_tri[1] +
        v[tri_mask][:, None] * src_tri[2]
    )
    dst_pts = pts[tri_mask].astype(np.int32)

    # ---- 遮罩筛选：只保留源像素在遮罩内的点 ----
    if mask_arr is not None:
        src_x_int = np.clip(src_pts[:, 0].astype(np.int32), 0, mask_arr.shape[1] - 1)
        src_y_int = np.clip(src_pts[:, 1].astype(np.int32), 0, mask_arr.shape[0] - 1)
        mask_vals = mask_arr[src_y_int, src_x_int]
        valid = mask_vals >= mask_threshold
        if not np.any(valid):
            return
        src_pts = src_pts[valid]
        dst_pts = dst_pts[valid]

    # ---- 双线性插值采样 ----
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

    dst_arr[dst_pts[:, 1], dst_pts[:, 0]] = np.clip(colors, 0, 255).astype(np.uint8)


def load_mask(mask_path, target_size):
    """加载遮罩图并缩放到目标尺寸，返回灰度 numpy 数组。"""
    mask_img = Image.open(mask_path)
    # 转为灰度：优先使用 L 模式，否则取各通道平均
    if mask_img.mode == 'L':
        mask_gray = mask_img
    elif mask_img.mode == 'RGBA':
        # 对于 RGBA，优先使用 alpha 通道，如果 alpha 全满则使用亮度
        arr = np.array(mask_img)
        if np.any(arr[:, :, 3] < 255):
            mask_gray = Image.fromarray(arr[:, :, 3])
        else:
            mask_gray = mask_img.convert('L')
    else:
        mask_gray = mask_img.convert('L')

    if mask_gray.size != target_size:
        # 使用最近邻缩放，保持硬边缘
        mask_gray = mask_gray.resize(target_size, Image.Resampling.NEAREST)
    return np.array(mask_gray)


def remap_skin_to_texture(json_path, skin_path, output_dir="remapped_textures", mask_path=None, mask_threshold=128, base_dir=None, drawable_ids=None, exclude_drawable_ids=None):
    # 1. 加载数据
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    model_info = data["model_info"]
    drawables = data["drawables"]
    canvas_pixel_w, canvas_pixel_h = model_info["canvas_size_pixel"]
    ppu = model_info["pixels_per_unit"]
    textures = model_info["textures"]

    print(f"画布像素尺寸: {canvas_pixel_w}x{canvas_pixel_h}")
    print(f"PixelsPerUnit: {ppu}")
    print(f"纹理数量: {len(textures)}")
    print(f"可绘制对象数量: {len(drawables)}")

    # 2. 加载新皮肤图，并缩放到画布像素尺寸
    skin_img = Image.open(skin_path).convert("RGBA")
    if skin_img.size != (canvas_pixel_w, canvas_pixel_h):
        print(f"注意: 新皮肤图尺寸 {skin_img.size} 与画布尺寸 {(canvas_pixel_w, canvas_pixel_h)} 不一致，已自动缩放")
        skin_img = skin_img.resize((canvas_pixel_w, canvas_pixel_h), Image.Resampling.LANCZOS)
    skin_arr = np.array(skin_img)

    # 3. 加载遮罩图（如有）
    mask_arr = None
    if mask_path is not None:
        if not os.path.exists(mask_path):
            print(f"警告: 遮罩文件不存在，忽略遮罩: {mask_path}")
        else:
            mask_arr = load_mask(mask_path, skin_img.size)
            print(f"已加载遮罩: {mask_path}，阈值: {mask_threshold}")
            print(f"遮罩有效像素数: {int(np.sum(mask_arr >= mask_threshold))} / {mask_arr.size}")

    # 4. 为每个纹理准备输出图像（复制原纹理作为基底，支持用上一步结果作为基底）
    texture_images = {}
    texture_sizes = {}
    for tex_path in textures:
        base_tex = None
        if base_dir is not None:
            base_path = os.path.join(base_dir, os.path.basename(tex_path))
            if os.path.exists(base_path):
                base_tex = Image.open(base_path).convert("RGBA")
                print(f"使用基底纹理: {base_path}")
        if base_tex is None:
            if os.path.exists(tex_path):
                base_tex = Image.open(tex_path).convert("RGBA")
            else:
                print(f"警告: 未找到原纹理 {tex_path}，创建空白 2048x2048 图像")
                base_tex = Image.new("RGBA", (2048, 2048), (0, 0, 0, 0))
        texture_images[tex_path] = np.array(base_tex)
        texture_sizes[tex_path] = base_tex.size

    # 5. 遍历每个 drawable，反向映射三角形（跳过不可见的 drawable）
    # 注意：Live2D 隐藏状态的 opacity 可能是极小的浮点数（如 5e-05），不是精确的 0
    visible_drawables = [d for d in drawables if d.get("opacity", 1.0) > 0.001]
    print(f"可见 drawable 数量: {len(visible_drawables)} / {len(drawables)}")

    # 进一步按 drawable ID 列表限制（如有）
    if drawable_ids is not None:
        allowed = set(id.strip() for id in drawable_ids.split(",") if id.strip())
        visible_drawables = [d for d in visible_drawables if d["id"] in allowed]
        print(f"进一步限制为指定 drawable: {len(visible_drawables)} 个")
        if not visible_drawables:
            print("警告: 没有匹配的 drawable，请检查 ID 拼写")

    # 排除指定的 drawable ID（黑名单模式，优先级高于 --drawables）
    if exclude_drawable_ids is not None:
        excluded = set(id.strip() for id in exclude_drawable_ids.split(",") if id.strip())
        before_count = len(visible_drawables)
        visible_drawables = [d for d in visible_drawables if d["id"] not in excluded]
        print(f"排除指定 drawable: {before_count - len(visible_drawables)} 个被排除，剩余 {len(visible_drawables)} 个")
        if not visible_drawables:
            print("警告: 排除后没有剩余的 drawable")
    skipped_tris = 0
    processed_tris = 0
    for d_idx, d in enumerate(visible_drawables):
        tex_file = d["texture_file"]
        if tex_file not in texture_images:
            print(f"跳过 drawable {d['id']}，纹理未加载: {tex_file}")
            continue

        tex_w, tex_h = texture_sizes[tex_file]
        dst_arr = texture_images[tex_file]

        # 模型空间顶点 → 新皮肤图像素坐标
        verts = d["vertices"]
        skin_pixels = []
        for vx, vy in verts:
            px = vx * ppu + canvas_pixel_w / 2.0
            py = canvas_pixel_h / 2.0 - vy * ppu
            skin_pixels.append((px, py))

        # UV → 纹理像素坐标
        uvs = d["uvs"]
        tex_pixels = []
        for u, v in uvs:
            tx = u * tex_w
            ty = v * tex_h
            tex_pixels.append((tx, ty))

        indices = d["indices"]
        tri_count = len(indices) // 3

        for i in range(tri_count):
            i0 = indices[i * 3]
            i1 = indices[i * 3 + 1]
            i2 = indices[i * 3 + 2]

            src_tri = [skin_pixels[i0], skin_pixels[i1], skin_pixels[i2]]
            dst_tri = [tex_pixels[i0], tex_pixels[i1], tex_pixels[i2]]

            # 快速剔除：如果三角形的三个顶点都在遮罩外，大概率不需要处理
            if mask_arr is not None:
                in_mask = False
                for p in src_tri:
                    sx, sy = int(p[0]), int(p[1])
                    if 0 <= sx < mask_arr.shape[1] and 0 <= sy < mask_arr.shape[0]:
                        if mask_arr[sy, sx] >= mask_threshold:
                            in_mask = True
                            break
                if not in_mask:
                    skipped_tris += 1
                    continue

            warp_triangle(skin_arr, dst_arr, src_tri, dst_tri, mask_arr, mask_threshold)
            processed_tris += 1

        if (d_idx + 1) % 10 == 0 or d_idx == len(drawables) - 1:
            print(f"  已处理 {d_idx + 1}/{len(drawables)} 个 drawable")

    if mask_arr is not None:
        print(f"\n遮罩优化: 跳过了 {skipped_tris} 个完全在遮罩外的三角形，处理了 {processed_tris} 个")

    # 6. 保存结果
    os.makedirs(output_dir, exist_ok=True)
    saved_paths = []
    for tex_path, arr in texture_images.items():
        base_name = os.path.basename(tex_path)
        name, ext = os.path.splitext(base_name)
        output_path = os.path.join(output_dir, f"{name}_new{ext}")
        Image.fromarray(arr).save(output_path)
        saved_paths.append(output_path)
        print(f"已保存: {output_path}")

    print("\n映射完成！")
    print("提示: 将生成的新纹理文件重命名为原纹理文件名，覆盖到模型目录下即可。")
    return saved_paths


def main():
    parser = argparse.ArgumentParser(
        description="将重绘好的完整角色图反向映射回 Live2D 纹理"
    )
    parser.add_argument("json", help="UV 数据 JSON 文件路径")
    parser.add_argument("skin", help="新皮肤 PNG 路径")
    parser.add_argument("output", nargs="?", default="remapped_textures", help="输出目录")
    parser.add_argument("--mask", default=None, help="遮罩图路径（白色=修改区域，黑色=保留区域）")
    parser.add_argument("--mask-threshold", type=int, default=128,
                        help="遮罩阈值，像素值>=此值视为有效修改区域（默认128）")
    parser.add_argument("--base-dir", default=None,
                        help="基底纹理目录（用于多套衣服逐套编辑，上一步的输出目录）")
    parser.add_argument("--drawables", default=None,
                        help="只映射指定 drawable，逗号分隔 ID 列表（如 'ArtMesh52,ArtMesh54,ArtMesh77'）")
    parser.add_argument("--exclude-drawables", default=None,
                        help="排除指定 drawable，逗号分隔 ID 列表（与 --mask 配合可实现粗略圈选后排除部件）")
    args = parser.parse_args()

    if not os.path.exists(args.json):
        print(f"错误: JSON 文件不存在: {args.json}")
        sys.exit(1)
    if not os.path.exists(args.skin):
        print(f"错误: 皮肤图片不存在: {args.skin}")
        sys.exit(1)

    try:
        remap_skin_to_texture(
            args.json, args.skin, args.output,
            mask_path=args.mask, mask_threshold=args.mask_threshold,
            base_dir=args.base_dir, drawable_ids=args.drawables,
            exclude_drawable_ids=args.exclude_drawables
        )
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
