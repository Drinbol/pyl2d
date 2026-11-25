# 利用 Live2D UV 数据生成贴图映射和 PSD

## 1. UV 数据是什么？

在 Live2D 中，每个 **drawable**（可绘制部件）由以下数据构成：
- **顶点位置** (vertices)：三维空间中的点（x, y, z），但通常 z=0。
- **顶点索引** (indices)：定义三角形面的顶点顺序。
- **UV 坐标** (uvs)：每个顶点在纹理贴图上的二维坐标 (u, v)，范围通常为 [0, 1]。
- **纹理索引** (texture index)：指向该 drawable 使用的纹理文件（如 `texture_00.png`）。

**UV 映射** 的本质是将三维网格的每个顶点“粘贴”到二维纹理的某个位置。例如，一个眼睛部件的顶点可能映射到纹理贴图中眼睛图案的区域。

## 2. 如何获取 UV 数据？

通过我们添加的 Python 接口，可以这样获取：

```python
# 假设 model 是已加载的 Live2D v3 模型
drawable_count = model.GetDrawableCount()
for i in range(drawable_count):
    vertices = model.GetDrawableVertices(i)        # 顶点位置列表 [(x1,y1), ...]
    uvs = model.GetDrawableVertexUvs(i)           # UV 坐标列表 [(u1,v1), ...]
    indices = model.GetDrawableIndices(i)         # 索引列表 [i1, i2, i3, ...]
    tex_index = model.GetDrawableTextureIndex(i)  # 纹理索引
```

**注意**：`GetDrawableVertices` 和 `GetDrawableIndices` 方法原本已存在（如果没有，可以类似添加）。

## 3. 如何将模型与贴图对应？

每个 drawable 使用一个纹理文件（可能多个 drawable 共享同一个纹理）。纹理文件通常命名为 `texture_00.png`、`texture_01.png` 等，纹理索引即对应编号。

**对应步骤**：
1. 根据纹理索引找到对应的纹理图片。
2. 对于该 drawable 的每个三角形（由三个索引定义），获取三个顶点的 UV 坐标。
3. 将 UV 坐标乘以纹理的宽度和高度，得到纹理像素坐标。
   ```python
   tex_width, tex_height = texture.size
   pixel_coords = [(u * tex_width, v * tex_height) for u, v in uvs]
   ```
4. 这样就得到了每个顶点在纹理上的精确位置。

**可视化**：你可以将顶点和三角形绘制到纹理图片上，以查看每个部件对应纹理的哪个区域。

## 4. 如何生成默认姿态的 PSD？

PSD（Photoshop 文档）是一种分层图像格式，每个 drawable 可以作为一个独立的图层。生成 PSD 的基本思路：

### 4.1 提取每个 drawable 的纹理区域
- 对于每个 drawable，根据其三角形和 UV 坐标，计算纹理上的 **包围盒**（bounding box）。
- 从纹理中裁剪出该区域，作为图层的图像内容。

### 4.2 创建图层
- 每个 drawable 对应一个 PSD 图层。
- 图层的位置和大小需要根据模型的 **顶点位置**（在默认姿态下）进行转换，因为 PSD 是二维平面，需要将三维顶点投影到画布上。

### 4.3 坐标转换
Live2D 模型有一个 **画布坐标系**（canvas），通常以模型中心为原点，单位是像素。你需要：
1. 获取画布尺寸：`canvas_width, canvas_height = model.GetCanvasSizePixel()`
2. 将顶点坐标转换为画布像素坐标（Live2D 的坐标系与屏幕坐标系可能有转换，通常需要 y 轴翻转）。
3. 根据顶点位置确定图层在画布上的位置（例如，图层的左上角坐标）。

### 4.4 生成 PSD 的步骤（伪代码）

```python
import psd_tools  # Python 库，用于创建 PSD 文件
from PIL import Image

# 1. 创建画布
canvas_width, canvas_height = model.GetCanvasSizePixel()
psd = psd_tools.PSDImage.new(canvas_width, canvas_height)

# 2. 遍历每个 drawable
for i in range(drawable_count):
    # 获取纹理索引和纹理图片
    tex_index = model.GetDrawableTextureIndex(i)
    texture = Image.open(f"texture_{tex_index:02d}.png")
    
    # 获取顶点和 UV
    vertices = model.GetDrawableVertices(i)
    uvs = model.GetDrawableVertexUvs(i)
    indices = model.GetDrawableIndices(i)
    
    # 计算纹理上的包围盒
    u_min = min(u for u, v in uvs)
    u_max = max(u for u, v in uvs)
    v_min = min(v for u, v in uvs)
    v_max = max(v for u, v in uvs)
    
    # 裁剪纹理区域
    left = int(u_min * texture.width)
    right = int(u_max * texture.width)
    top = int(v_min * texture.height)
    bottom = int(v_max * texture.height)
    layer_image = texture.crop((left, top, right, bottom))
    
    # 计算图层在画布上的位置（以包围盒中心为参考）
    # 需要将顶点坐标转换为画布像素坐标
    # 这里简化：取顶点平均值作为图层中心
    avg_x = sum(v[0] for v in vertices) / len(vertices)
    avg_y = sum(v[1] for v in vertices) / len(vertices)
    # 转换为画布坐标（具体转换公式需根据 Live2D 坐标系调整）
    canvas_x = avg_x + canvas_width / 2
    canvas_y = canvas_height / 2 - avg_y  # 假设 y 轴向上
    
    # 创建图层
    layer = psd_tools.Layer.new(canvas_width, canvas_height, name=f"drawable_{i}")
    layer.offset = (int(canvas_x - layer_image.width / 2), int(canvas_y - layer_image.height / 2))
    layer.image = layer_image
    psd.add_layer(layer)

# 3. 保存 PSD
psd.save("model_default_pose.psd")
```

### 4.5 注意事项
- **图层顺序**：Live2D 绘制有前后顺序（通过 `GetDrawableRenderOrder` 获取），PSD 图层应按此顺序排列。
- **透明度**：纹理可能包含 Alpha 通道，需保留。
- **变形**：默认姿态下顶点位置是静态的，但 Live2D 模型可能包含网格变形（通过参数驱动）。生成 PSD 时使用默认参数值（即初始姿态）。
- **性能**：如果 drawable 数量很多（几百个），PSD 文件可能很大。

## 5. 完整的工作流程

1. **提取数据**：使用修改后的 live2d-py 获取所有 drawable 的顶点、UV、索引、纹理索引。
2. **加载纹理**：读取模型目录下的纹理图片。
3. **计算图层图像**：根据 UV 裁剪纹理。
4. **计算图层位置**：根据顶点位置和画布尺寸确定图层在 PSD 中的位置。
5. **创建 PSD**：使用 `psd-tools` 或 `photoshop-python-api` 等库生成分层 PSD。
6. **验证**：在 Photoshop 中打开 PSD，检查图层是否正确对应模型部件。

## 6. 工具推荐

- **psd-tools**：Python 库，可以读写 PSD 文件（但不支持所有 Photoshop 功能）。
- **Pillow**：用于图像处理。
- **OpenCV**：可选，用于更复杂的图像处理。

## 7. 总结

通过我们添加的 UV 接口，你现在可以获取 Live2D 模型的纹理映射数据。结合顶点位置和纹理图片，你可以生成一个分层的 PSD 文件，其中每个图层对应一个模型部件，并且图层位置与模型默认姿态对齐。这为后续的贴图编辑、动画制作等提供了基础。

如果你需要具体的代码实现，我可以进一步提供示例脚本。