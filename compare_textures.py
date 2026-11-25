#!/usr/bin/env python3
"""
对比新旧纹理的非透明区域差异，生成差异图和统计报告。

用法:
    python compare_textures.py <旧纹理> <新纹理> [输出目录]
    
示例:
    python compare_textures.py old/texture_00.png new/texture_00_new.png diff_output
"""
import argparse
import os
import sys
import numpy as np
from PIL import Image


def compare_textures(old_path, new_path, output_dir="diff_output"):
    old_img = Image.open(old_path).convert("RGBA")
    new_img = Image.open(new_path).convert("RGBA")

    # 统一尺寸
    w, h = old_img.size
    if new_img.size != old_img.size:
        print(f"注意: 尺寸不一致，新纹理 {new_img.size} 已缩放至 {old_img.size}")
        new_img = new_img.resize((w, h), Image.Resampling.LANCZOS)

    old_arr = np.array(old_img).astype(np.float32)
    new_arr = np.array(new_img).astype(np.float32)

    # 非透明 mask
    old_mask = old_arr[:, :, 3] > 10
    new_mask = new_arr[:, :, 3] > 10
    combined_mask = old_mask | new_mask

    # 逐通道绝对差值
    diff = np.abs(old_arr - new_arr)
    diff_rgb = diff[:, :, :3]
    max_diff = np.max(diff_rgb, axis=2)

    # 只在非透明区域统计差异
    masked_max_diff = np.where(combined_mask, max_diff, 0)

    # 统计
    total_pixels = w * h
    changed_pixels = int(np.sum((masked_max_diff > 5) & combined_mask))
    changed_ratio = changed_pixels / np.sum(combined_mask) * 100 if np.sum(combined_mask) > 0 else 0
    mean_diff = float(np.mean(masked_max_diff[combined_mask])) if np.sum(combined_mask) > 0 else 0
    max_diff_val = float(np.max(masked_max_diff)) if np.sum(combined_mask) > 0 else 0

    print(f"\n=== 差异统计 ===")
    print(f"旧纹理: {old_path}")
    print(f"新纹理: {new_path}")
    print(f"尺寸: {w}x{h}")
    print(f"非透明像素数: {int(np.sum(combined_mask))} / {total_pixels}")
    print(f"变化像素数 (>5/255): {changed_pixels}")
    print(f"变化占比 (在非透明区域中): {changed_ratio:.2f}%")
    print(f"平均差异: {mean_diff:.2f}/255")
    print(f"最大差异: {max_diff_val:.2f}/255")

    # 生成差异图
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(old_path))[0]

    # 1. 纯差异热力图（红=大差异，黑=无差异）
    heatmap = np.zeros((h, w, 3), dtype=np.uint8)
    norm_diff = np.clip(masked_max_diff / 255.0, 0, 1)
    # 使用热图颜色：黑(0) -> 红(1)
    heatmap[:, :, 0] = (norm_diff * 255).astype(np.uint8)
    heatmap[:, :, 1] = 0
    heatmap[:, :, 2] = 0
    heatmap_img = Image.fromarray(heatmap)
    heatmap_path = os.path.join(output_dir, f"{base_name}_diff_heatmap.png")
    heatmap_img.save(heatmap_path)
    print(f"差异热力图: {heatmap_path}")

    # 2. 叠加差异图（新纹理 + 红色高亮差异区域）
    overlay = new_arr.copy()
    significant = masked_max_diff > 5
    # 差异区域标红
    overlay[significant, 0] = 255
    overlay[significant, 1] = 0
    overlay[significant, 2] = 0
    # 保持原 alpha
    overlay[:, :, 3] = new_arr[:, :, 3]
    overlay_img = Image.fromarray(np.clip(overlay, 0, 255).astype(np.uint8))
    overlay_path = os.path.join(output_dir, f"{base_name}_diff_overlay.png")
    overlay_img.save(overlay_path)
    print(f"叠加差异图: {overlay_path}")

    # 3. 透明区域变化图（显示新增/消失的透明区域）
    alpha_diff = np.abs(old_arr[:, :, 3] - new_arr[:, :, 3])
    alpha_mask = alpha_diff > 10
    alpha_vis = np.zeros((h, w, 4), dtype=np.uint8)
    # 绿色 = 新增不透明
    alpha_vis[(~old_mask) & new_mask] = [0, 255, 0, 255]
    # 蓝色 = 消失的不透明
    alpha_vis[old_mask & (~new_mask)] = [0, 0, 255, 255]
    # 红色 = 两者都不透明但有颜色差异
    alpha_vis[old_mask & new_mask & (masked_max_diff > 5)] = [255, 0, 0, 255]
    alpha_img = Image.fromarray(alpha_vis)
    alpha_path = os.path.join(output_dir, f"{base_name}_diff_alpha.png")
    alpha_img.save(alpha_path)
    print(f"透明区域变化图 (绿=新增, 蓝=消失, 红=颜色变化): {alpha_path}")

    return {
        "changed_pixels": changed_pixels,
        "changed_ratio": changed_ratio,
        "mean_diff": mean_diff,
        "max_diff": max_diff_val,
    }


def main():
    parser = argparse.ArgumentParser(description="对比新旧纹理差异")
    parser.add_argument("old", help="旧纹理 PNG 路径")
    parser.add_argument("new", help="新纹理 PNG 路径")
    parser.add_argument("output", nargs="?", default="diff_output", help="输出目录")
    args = parser.parse_args()

    if not os.path.exists(args.old):
        print(f"错误: 旧纹理不存在: {args.old}")
        sys.exit(1)
    if not os.path.exists(args.new):
        print(f"错误: 新纹理不存在: {args.new}")
        sys.exit(1)

    compare_textures(args.old, args.new, args.output)


if __name__ == "__main__":
    main()
