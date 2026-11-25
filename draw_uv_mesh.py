#!/usr/bin/env python3
"""
在纹理图片上绘制UV三角形网格，验证UV映射的正确性。
输入：extract_uv_data.py 生成的JSON文件
输出：带有三角形网格的纹理PNG图片
"""
import json
from PIL import Image, ImageDraw
import random
import sys
import os

def load_texture(texture_path):
    """加载纹理图片，如果路径不存在则尝试相对路径。"""
    if os.path.exists(texture_path):
        return Image.open(texture_path).convert("RGBA")
    # 尝试相对于当前目录
    cwd = os.getcwd()
    alt_path = os.path.join(cwd, texture_path)
    if os.path.exists(alt_path):
        return Image.open(alt_path).convert("RGBA")
    else:
        print(f"警告: 纹理文件未找到: {texture_path}")
        # 创建空白图像作为占位符
        return Image.new("RGBA", (2048, 2048), (255, 255, 255, 0))

def draw_mesh_on_texture(json_path, output_dir="uv_mesh_output"):
    """读取JSON数据，在每个纹理上绘制可绘制对象的三角形网格。"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    model_info = data["model_info"]
    drawables = data["drawables"]
    textures = model_info["textures"]
    
    # 为每个纹理创建图像副本
    texture_images = {}
    for tex_path in textures:
        img = load_texture(tex_path)
        texture_images[tex_path] = img.copy()
    
    # 为每个可绘制对象分配随机颜色
    colors = {}
    for d in drawables:
        if d["texture_file"] not in colors:
            # 生成半透明颜色
            colors[d["texture_file"]] = (
                random.randint(50, 255),
                random.randint(50, 255),
                random.randint(50, 255),
                180  # 透明度
            )
    
    # 绘制每个可绘制对象
    for d in drawables:
        tex_file = d["texture_file"]
        if tex_file not in texture_images:
            print(f"跳过可绘制对象 {d['id']}，纹理未加载: {tex_file}")
            continue
        
        img = texture_images[tex_file]
        draw = ImageDraw.Draw(img, "RGBA")
        color = colors[tex_file]
        
        uvs = d["uvs"]
        indices = d["indices"]
        vertex_count = d["vertex_count"]
        
        # 将UV坐标转换为像素坐标
        width, height = img.size
        uv_pixels = [(int(u * width), int(v * height)) for u, v in uvs]
        
        # 绘制三角形
        for i in range(0, len(indices), 3):
            if i + 2 >= len(indices):
                break
            idx0 = indices[i]
            idx1 = indices[i + 1]
            idx2 = indices[i + 2]
            if idx0 >= vertex_count or idx1 >= vertex_count or idx2 >= vertex_count:
                print(f"警告: 索引超出范围，跳过三角形")
                continue
            triangle = [uv_pixels[idx0], uv_pixels[idx1], uv_pixels[idx2]]
            # 绘制填充三角形（半透明）
            draw.polygon(triangle, fill=color, outline=None)
            # 绘制三角形边框（黑色）
            draw.line([triangle[0], triangle[1], triangle[2], triangle[0]], fill=(0, 0, 0, 255), width=1)
        
        # 在包围盒中心绘制索引编号，带黑色描边背景
        if uv_pixels:
            xs = [p[0] for p in uv_pixels]
            ys = [p[1] for p in uv_pixels]
            cx = int(sum(xs) / len(xs))
            cy = int(sum(ys) / len(ys))
            text = str(d["index"])
            # 黑色描边
            for dx, dy in [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]:
                draw.text((cx + dx, cy + dy), text, fill=(0, 0, 0, 255))
            # 黄色主文字
            draw.text((cx, cy), text, fill=(255, 255, 0, 255))
    
    # 保存输出
    os.makedirs(output_dir, exist_ok=True)
    for tex_path, img in texture_images.items():
        base_name = os.path.basename(tex_path)
        name, ext = os.path.splitext(base_name)
        output_path = os.path.join(output_dir, f"{name}_mesh{ext}")
        img.save(output_path)
        print(f"已保存: {output_path}")
    
    # 同时创建一个合并所有纹理的图片（如果多个纹理）
    if len(texture_images) > 1:
        # 水平拼接
        images = list(texture_images.values())
        total_width = sum(img.width for img in images)
        max_height = max(img.height for img in images)
        combined = Image.new("RGBA", (total_width, max_height))
        x_offset = 0
        for img in images:
            combined.paste(img, (x_offset, 0))
            x_offset += img.width
        combined.save(os.path.join(output_dir, "combined_mesh.png"))
        print(f"已保存合并图片: {os.path.join(output_dir, 'combined_mesh.png')}")
    
    print("绘制完成！")

def main():
    if len(sys.argv) < 2:
        print("用法: python draw_uv_mesh.py <JSON文件路径> [输出目录]")
        print("示例: python draw_uv_mesh.py haru_uv_data.json uv_mesh_output")
        sys.exit(1)
    
    json_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) >= 3 else "uv_mesh_output"
    
    if not os.path.exists(json_path):
        print(f"错误: JSON文件不存在: {json_path}")
        sys.exit(1)
    
    try:
        draw_mesh_on_texture(json_path, output_dir)
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()