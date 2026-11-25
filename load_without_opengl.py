"""
演示如何使用 live2d.v3.Model 在不创建 OpenGL 上下文的情况下加载模型。
这对于 Qt+ModernGL 环境很有用，可以避免 OpenGL 上下文冲突。
"""
import live2d.v3 as live2d_v3
import live2d
import os
import sys

def main():
    # 1. 初始化 Live2D 内存分配器
    live2d_v3.init()
    
    # 2. 创建 Model 实例
    model = live2d_v3.Model()
    
    # 3. 加载模型 JSON 文件（不需要 OpenGL 上下文）
    # 我们需要找到模型文件的路径。假设我们使用包内附带的 Haru 模型。
    # 首先，获取 live2d 包的安装路径
    package_dir = os.path.dirname(live2d.__file__)
    # 资源目录通常位于包目录的上一级，即 live2d-py/Resources
    # 但具体位置取决于安装方式。这里我们使用相对路径。
    # 如果找不到，可以尝试使用绝对路径。
    resources_dir = os.path.join(package_dir, '..', 'Resources')
    resources_dir = os.path.abspath(resources_dir)
    print(f"资源目录: {resources_dir}")
    
    # 检查目录是否存在
    if not os.path.exists(resources_dir):
        print("警告: 资源目录不存在，尝试使用当前工作目录下的 live2d-py/Resources")
        # 回退到当前目录下的 live2d-py/Resources
        resources_dir = os.path.join(os.getcwd(), 'live2d-py', 'Resources')
    
    # 使用新的 boy 模型路径
    boy_model_dir = r'D:\Software\Tool\Steam\steamapps\common\StudentAge\data\L2DModels\girl2'
    model_json_path = os.path.join(boy_model_dir, 'girl2.model3.json')
    if not os.path.exists(model_json_path):
        print(f"错误: 模型文件不存在: {model_json_path}")
        # 尝试其他路径
        # 列出可能的路径
        possible_paths = [
            os.path.join(boy_model_dir, 'girl2.model3.json'),
            os.path.join(resources_dir, 'v3', 'Haru', 'Haru.model3.json'),
            os.path.join(resources_dir, 'v3', 'Mao', 'Mao.model3.json'),
            os.path.join(resources_dir, 'v3', 'nn', 'nn.model3.json'),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                model_json_path = path
                print(f"使用模型: {path}")
                break
        else:
            print("未找到任何模型文件，请确保资源文件已安装。")
            sys.exit(1)
    
    print(f"加载模型: {model_json_path}")
    model.LoadModelJson(model_json_path)
    
    # 4. 获取模型信息（不需要 OpenGL 上下文）
    print("\n=== 模型信息 ===")
    print(f"模型目录: {model.GetModelHomeDir()}")
    print(f"画布大小: {model.GetCanvasSize()}")
    print(f"画布像素大小: {model.GetCanvasSizePixel()}")
    print(f"每单位像素: {model.GetPixelsPerUnit()}")
    
    param_ids = model.GetParameterIds()
    print(f"参数数量: {len(param_ids)}")
    if len(param_ids) > 0:
        print(f"前5个参数: {param_ids[:5]}")
    
    part_ids = model.GetPartIds()
    print(f"部件数量: {len(part_ids)}")
    if len(part_ids) > 0:
        print(f"前5个部件: {part_ids[:5]}")
    
    drawable_ids = model.GetDrawableIds()
    print(f"可绘制对象数量: {len(drawable_ids)}")
    if len(drawable_ids) > 0:
        print(f"前5个可绘制对象: {drawable_ids[:5]}")
    
    expressions = model.GetExpressions()
    print(f"表情数量: {len(expressions)}")
    if len(expressions) > 0:
        print(f"表情: {expressions[:5]}")
    
    motions = model.GetMotions()
    print(f"动作组数量: {len(motions)}")
    for group, motion_list in motions.items():
        print(f"  组 '{group}': {len(motion_list)} 个动作")
    
    # 5. 加载额外动作（可选）
    extra_motion_path = os.path.join(resources_dir, 'v3', 'public_motions', 'drag_down.motion3.json')
    if os.path.exists(extra_motion_path):
        motion_index = model.LoadExtraMotion("extra", extra_motion_path)
        print(f"加载额外动作，索引: {motion_index}")
    
    # 6. 现在，我们可以进行模型更新（不需要 OpenGL 上下文）
    # 更新模型状态（例如，设置参数）
    # 注意：在没有渲染器的情况下，我们仍然可以更新参数，但无法绘制。
    print("\n=== 更新模型参数 ===")
    if len(param_ids) > 0:
        # 获取第一个参数的当前值
        value = model.GetParameterValue(0)
        print(f"参数 '{param_ids[0]}' 当前值: {value}")
        # 设置新值
        model.SetParameterValue(0, value + 0.1)
        new_value = model.GetParameterValue(0)
        print(f"设置后值: {new_value}")
    
    # 7. 模拟一帧更新
    delta_time = 0.033  # 约 30 FPS
    model.LoadParameters()
    model.UpdateMotion(delta_time)
    model.UpdateBlink(delta_time)
    model.UpdateExpression(delta_time)
    model.UpdateBreath(delta_time)
    model.UpdatePhysics(delta_time)
    model.UpdatePose(delta_time)
    model.SaveParameters()
    
    print("\n=== 模型加载完成，可以稍后创建渲染器 ===")
    print("""
    要在 Qt+ModernGL 环境中使用：
    1. 在 OpenGL 上下文创建后，调用 live2d_v3.glInit()
    2. 调用 model.CreateRenderer(maskBufferCount=2)
    3. 调整窗口大小：model.Resize(width, height)
    4. 在渲染循环中：
        - 更新模型：调用上述 Update* 方法
        - 清除缓冲区：live2d_v3.clearBuffer()
        - 绘制：model.Draw()
    5. 退出时，销毁渲染器：model.DestroyRenderer()
    6. 调用 live2d_v3.dispose()
    """)
    
    # 注意：由于我们没有创建 OpenGL 上下文，因此不能调用 CreateRenderer 和 Draw。
    # 这里我们只是演示加载和更新。
    
    # 清理（可选，因为程序即将退出）
    # live2d_v3.dispose()

if __name__ == "__main__":
    main()