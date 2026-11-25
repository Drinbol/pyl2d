#!/usr/bin/env python3
"""
从Live2D模型中提取UV映射、几何数据和遮罩信息，用于生成PSD。

图层命名规则: "index:id" 格式，如 "3:ArmL" —— 这样在PSD中按名称排序时
能保持Live2D原始绘制顺序。

遮罩信息提取流程:
  1. GetDrawableMaskCounts() 返回每个drawable的遮罩数量（从C++暴露）
  2. GetDrawableMasks() 返回每个drawable的遮罩drawable索引列表（从C++暴露）
  3. GetDrawableInvertedMask(idx) 判断遮罩是否反转（从C++暴露）

生成的JSON中包含完整遮罩数据，uv_to_psd脚本可利用这些信息创建正确的图层遮罩。
"""
import live2d.v3 as live2d
import os
import json
import sys
from pathlib import Path


def find_texture_files(model_dir):
    """在模型目录中查找纹理文件。
    假设纹理文件位于模型目录下的子目录中，如 '*.2048/texture_*.png'。
    返回纹理文件路径列表，按索引排序。
    """
    textures = []
    model_path = Path(model_dir)
    # 查找包含纹理文件的子目录
    for subdir in model_path.iterdir():
        if subdir.is_dir() and subdir.name.startswith(model_path.name):
            # 例如 Haru.2048
            for tex_file in subdir.glob("texture_*.png"):
                textures.append(str(tex_file))
    # 按文件名排序，确保索引顺序正确
    textures.sort()
    return textures


def extract_model_data(model_json_path, params=None):
    """加载模型并提取所有可绘制对象的数据。
    
    Args:
        model_json_path: 模型 JSON 路径
        params: 可选，参数设置字典，如 {"ParamCloth": 1.0}
    """
    live2d.init()
    model = live2d.Model()
    
    print(f"加载模型: {model_json_path}")
    model.LoadModelJson(model_json_path)
    
    # 设置参数（如有）
    if params:
        for param_id, value in params.items():
            try:
                model.SetParameterValueById(param_id, float(value))
                print(f"设置参数: {param_id} = {value}")
            except Exception as e:
                print(f"警告: 无法设置参数 {param_id}: {e}")
        # 必须先 SaveParameters，否则 Update 里的 LoadParameters 会把参数覆盖回默认值
        model.SaveParameters()
        model.Update(0.0)
    
    model_dir = model.GetModelHomeDir()
    print(f"模型目录: {model_dir}")
    
    # 查找纹理文件
    texture_files = find_texture_files(model_dir)
    if not texture_files:
        # 回退：在模型目录中直接查找
        model_path = Path(model_dir)
        for tex_file in model_path.glob("*.png"):
            texture_files.append(str(tex_file))
        texture_files.sort()
    
    print(f"找到纹理文件: {texture_files}")
    
    # 获取模型信息
    canvas_size = model.GetCanvasSize()
    canvas_size_pixel = model.GetCanvasSizePixel()
    pixels_per_unit = model.GetPixelsPerUnit()
    
    # 获取可绘制对象ID、绘制顺序、不透明度和所属部件
    drawable_ids = model.GetDrawableIds()
    render_orders = model.GetDrawableRenderOrders()
    opacities = model.GetDrawableOpacities()
    parent_part_indices = model.GetDrawableParentPartIndices()
    print(f"可绘制对象数量: {len(drawable_ids)}")
    
    # 获取遮罩信息
    mask_counts = model.GetDrawableMaskCounts()
    mask_indices_list = model.GetDrawableMasks()
    print(f"遮罩信息已获取")
    
    drawables = []
    for idx, drawable_id in enumerate(drawable_ids):
        if idx % 10 == 0:
            print(f"  处理 {idx}/{len(drawable_ids)}...")
        
        try:
            vertex_count = model.GetDrawableVertexCount(idx)
            vertices = model.GetDrawableVertices(idx)
            uvs = model.GetDrawableVertexUvs(idx)
            # 翻转V坐标（上下翻转），因为Live2D内部使用左下角原点，而纹理图片使用左上角原点
            uvs = [(u, 1.0 - v) for u, v in uvs]
            indices = model.GetDrawableIndices(idx)
            texture_index = model.GetDrawableTextureIndex(idx)
            
            # 计算边界框（模型坐标系）
            if vertices:
                xs = [v[0] for v in vertices]
                ys = [v[1] for v in vertices]
                bbox = {
                    "xmin": min(xs),
                    "ymin": min(ys),
                    "xmax": max(xs),
                    "ymax": max(ys)
                }
            else:
                bbox = None
            
            # 确定纹理文件名
            texture_file = None
            if 0 <= texture_index < len(texture_files):
                texture_file = texture_files[texture_index]
            else:
                texture_file = f"texture_{texture_index:02d}.png"
            
            # 构建遮罩信息：通过mask中的drawable索引找到对应的drawable ID
            mask_drawable_indices = []
            mask_count = mask_counts[idx]
            if mask_count > 0:
                mask_drawable_indices = mask_indices_list[idx]
            
            # 判断是否反转遮罩
            inverted_mask = model.GetDrawableInvertedMask(idx)
            
            # 图层名: "index:id" 格式确保按名称排序时保持Live2D的绘制顺序
            layer_name = f"{idx}:{drawable_id}"
            
            drawable = {
                "id": drawable_id,
                "index": idx,
                "layer_name": layer_name,
                "render_order": render_orders[idx],
                "opacity": opacities[idx],
                "parent_part_index": parent_part_indices[idx],
                "vertex_count": vertex_count,
                "vertices": vertices,  # 列表的列表
                "uvs": uvs,
                "indices": indices,
                "texture_index": texture_index,
                "texture_file": texture_file,
                "bounding_box": bbox,
                "blend_mode": "normal",  # 默认值
                # 遮罩信息
                "mask_count": mask_count,
                "mask_drawable_indices": mask_drawable_indices,
                "mask_drawable_ids": [drawable_ids[mi] for mi in mask_drawable_indices] if mask_drawable_indices else [],
                "inverted_mask": inverted_mask,
            }
            drawables.append(drawable)
        except Exception as e:
            print(f"    错误处理可绘制对象 {idx} ({drawable_id}): {e}")
            # 跳过有问题的可绘制对象
    
    # 按 render_order 排序，确保输出顺序与Live2D绘制顺序一致
    drawables.sort(key=lambda d: d["render_order"])
    
    # 构建输出数据结构
    output = {
        "model_info": {
            "name": Path(model_json_path).stem,
            "model_json": model_json_path,
            "model_dir": model_dir,
            "canvas_size": canvas_size,
            "canvas_size_pixel": canvas_size_pixel,
            "pixels_per_unit": pixels_per_unit,
            "textures": texture_files
        },
        "drawables": drawables
    }
    
    return output

def save_json(data, output_path):
    """将数据保存为JSON文件。"""
    # 自定义序列化器，处理元组等类型
    class CustomEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, tuple):
                return list(obj)
            return super().default(obj)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, cls=CustomEncoder, ensure_ascii=False)
    print(f"数据已保存到: {output_path}")

def main():
    if len(sys.argv) < 2:
        print("用法: python extract_uv_data.py <model3.json路径> [输出JSON路径] [--param 参数ID=值 ...]")
        print(r"示例: python extract_uv_data.py boy.model3.json boy_uv_data.json --param ParamCloth=1")
        sys.exit(1)
    
    model_json_path = sys.argv[1]
    output_path = None
    params = {}
    
    # 解析参数
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--param" and i + 1 < len(sys.argv):
            param_str = sys.argv[i + 1]
            if "=" in param_str:
                key, value = param_str.split("=", 1)
                params[key] = float(value)
            else:
                print(f"警告: 参数格式错误，应为 ID=值: {param_str}")
            i += 2
        else:
            if output_path is None:
                output_path = arg
            i += 1
    
    if output_path is None:
        model_name = Path(model_json_path).stem
        output_path = f"{model_name}_uv_data.json"
    
    if not os.path.exists(model_json_path):
        print(f"错误: 模型文件不存在: {model_json_path}")
        sys.exit(1)
    
    try:
        data = extract_model_data(model_json_path, params)
        save_json(data, output_path)
        print("提取完成！")
    except Exception as e:
        print(f"提取过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        live2d.dispose()

if __name__ == "__main__":
    main()