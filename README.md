# pyl2d - Live2D 纹理重绘工作流

一套围绕 [live2d-py](https://github.com/EasyLive2D/live2d-py) 构建的辅助脚本，用于将 Live2D 模型的默认姿态渲染为参考图、在参考图上重绘、再反向映射回模型纹理，并验证差异。

核心解决三个问题：
1. **绘制顺序**：软件渲染严格遵循 Live2D 的 `RenderOrder`，部件不会前后错乱
2. **隐藏部件污染**：自动跳过 `opacity <= 0` 的 drawable，被参数隐藏的部件从始至终不参与
3. **多套衣服合并**：支持参数切换后逐套编辑，通过 `--base-dir` 合并到同一张纹理

> **重要修复**：Live2D 隐藏状态的 opacity 不是精确的 `0.0`，而是极小的浮点数（如 `5e-05`）。所有脚本已采用 `> 0.001` 作为可见性阈值，避免隐藏部件被意外绘制/映射。

---

## 环境要求

- Python >= 3.14
- numpy, Pillow（已包含在 live2d-py 环境中）
- live2d-py（需自行编译，见下方说明）
- psd-tools（如需要 PSD 相关功能）

---

## 核心概念

### UV 映射
Live2D 的每个 **drawable**（可绘制部件）由三角形网格构成。每个顶点有两个坐标：
- **模型空间坐标**（vertices）：决定部件在屏幕上的位置和形状
- **UV 坐标**（uvs）：决定部件使用纹理上的哪个像素

### Render Order（绘制顺序）
Live2D 不是按 drawable 的索引顺序绘制的。每个 drawable 有一个 `render_order` 值，值越小越先绘制（在后层），值越大越后绘制（在前层）。本项目的软件渲染严格按此顺序执行，确保头发不会跑到脸前面。

### Opacity（不透明度）
Live2D 模型中很多 drawable 在默认状态下是隐藏的（`opacity=0`），例如：
- 被参数切换掉的衣服
- 闭眼时才显示的眼皮
- 张嘴时才显示的口腔内部

脚本会自动过滤 `opacity <= 0.001` 的 drawable，这些部件既不会出现在参考图上，也不会在反向映射时被污染。

> **注意**：如果你发现隐藏部件仍然出现，请重新提取 JSON（旧 JSON 中的 `opacity` 阈值是 `> 0`，已废弃）。

### 参数切换换装
很多模型没有多套独立的纹理文件，而是通过参数（如 `ParaClothSchool`）控制部件显隐来实现换装。参数值为 0 时显示校服，为 1 时隐藏校服、显示泳装。本工作流支持提取任意参数状态下的数据，分别编辑后合并到同一张纹理。

---

## 完整工作流

### 单套衣服编辑（最简单场景）

```bash
# Step 1：提取模型 UV 数据
python extract_uv_data.py D:\模型目录\角色.model3.json 角色_uv_data.json

# Step 2：渲染默认姿态参考图
python render_default_pose.py 角色_uv_data.json 角色_参考图.png

## psd模式
python .\render_default_pose.py .\work\default.json aaa2.psd --psd

# Step 3：在 Photoshop/SAI 中重绘参考图
# - 只修改需要替换的部分
# - （推荐）另存一张同尺寸的遮罩图：白色=修改区域，黑色=保留区域

# Step 4：反向映射回纹理
python remap_skin_to_texture.py 角色_uv_data.json 修改后的图.png remapped_textures \
    --mask 遮罩.png --mask-threshold 128

# 或者：遮罩圈大了，排除掉不想改的部件
python remap_skin_to_texture.py 角色_uv_data.json 修改后的图.png remapped_textures \
    --mask 遮罩.png --exclude-drawables ArtMesh52,ArtMesh54

# Step 5：差异对比验证
python compare_textures.py 原纹理\texture_00.png remapped_textures\texture_00_new.png diff_output
```

### 多套衣服编辑（参数切换换装）

假设模型有一个 `ParaClothSchool` 参数：0=校服，1=泳装。

```bash
# ========== 第 1 套：默认状态（校服） ==========
python extract_uv_data.py model.json data_school.json
python render_default_pose.py data_school.json ref_school.png
# 用户在 ref_school.png 上只改校服，保存 edited_school.png，制作遮罩 mask_school.png
python remap_skin_to_texture.py data_school.json edited_school.png --mask mask_school.png
# 输出 remapped_textures/texture_00_new.png（校服已改，泳装还是原样）

# ========== 第 2 套：ParaClothSchool=1（泳装） ==========
python extract_uv_data.py model.json data_swim.json --param ParaClothSchool=1
python render_default_pose.py data_swim.json ref_swim.png
# 用户在 ref_swim.png 上只改泳装，保存 edited_swim.png，制作遮罩 mask_swim.png
# 关键：用 --base-dir 指定上一步的输出目录作为基底
python remap_skin_to_texture.py data_swim.json edited_swim.png \
    --mask mask_swim.png --base-dir remapped_textures
# 最终 remapped_textures/texture_00_new.png 同时包含校服和泳装的修改
```

**为什么不会互相污染？**

| 步骤 | 校服 opacity | 泳装 opacity | 脚本行为 |
|------|-------------|-------------|---------|
| 提取校服状态 | 1.0 | 0.0 | 只渲染/映射校服的 drawable |
| 提取泳装状态 | 0.0 | 1.0 | 只渲染/映射泳装的 drawable |

`render_default_pose.py` 和 `remap_skin_to_texture.py` 都会自动跳过 `opacity <= 0` 的 drawable，所以两套衣服永远不会互相触碰。

**多套纹理的合并原理**

`--base-dir` 的作用是让第 2 步不再从原模型纹理开始，而是以第 1 步的结果为基底。因为不同衣服的 UV 区域通常位于纹理的不同位置，映射校服时不会碰泳装的像素，映射泳装时也不会碰校服的像素，最终自然合并为一张完整的纹理。

> **前提**：不同衣服的 UV 区域不重叠。规范的 Live2D 模型通常会把不同衣服放在纹理的不同位置。如果模型设计者故意让多套衣服共用同一个 UV 区域（极少见），那是模型结构限制，任何工具都无法在单张纹理上同时保留多套独立衣服。

---

## 脚本详细说明

### extract_uv_data.py

从 `.model3.json` 提取所有 drawable 的几何数据和 UV 映射信息。

```bash
python extract_uv_data.py <model3.json路径> [输出JSON路径] [选项]
```

| 参数 | 说明 |
|------|------|
| `model3.json` | 模型配置文件路径（必填） |
| `输出JSON路径` | 输出文件路径（可选，默认 `<模型名>_uv_data.json`） |
| `--param ID=值` | 设置模型参数后再提取，可多次使用。例如 `--param ParaClothSchool=1 --param ParamEyeOpen=0` |

**输出 JSON 结构**：

```json
{
  "model_info": {
    "name": "boy",
    "canvas_size_pixel": [2479, 3508],
    "pixels_per_unit": 261.0,
    "textures": ["work/texture_00.png"]
  },
  "drawables": [
    {
      "id": "artMesh1",
      "index": 0,
      "render_order": 167,
      "opacity": 1.0,
      "parent_part_index": 5,
      "vertex_count": 4,
      "vertices": [[-1.2, 0.5], ...],
      "uvs": [[0.1, 0.2], ...],
      "indices": [0, 1, 2, ...],
      "texture_index": 0,
      "texture_file": "work/texture_00.png"
    }
  ]
}
```

**字段说明**：

| 字段 | 说明 |
|------|------|
| `render_order` | 绘制顺序，值越大越在上层 |
| `opacity` | 该 drawable 在当前参数状态下的不透明度 |
| `parent_part_index` | 该 drawable 所属的 part 索引 |
| `vertices` | 模型空间坐标，用于确定屏幕位置 |
| `uvs` | 纹理坐标，范围 [0, 1]，已翻转 V 轴适配 Pillow |
| `indices` | 三角形顶点索引，每 3 个一组 |

---

### render_default_pose.py

纯软件光栅化渲染默认姿态参考图，无需 OpenGL / 窗口。

```bash
python render_default_pose.py <UV数据JSON> [输出PNG] [选项]
```

| 参数 | 说明 |
|------|------|
| `UV数据JSON` | `extract_uv_data.py` 生成的 JSON（必填） |
| `输出PNG` | 输出图片路径（可选，默认 `default_pose.png`） |
| `--texture-dir <目录>` | 替换纹理目录，用于加载非默认纹理 |
| `--batch` | 批量模式：`--texture-dir` 下的每个子目录视为一套皮肤，全部生成 |
| `--bg R G B A` | 背景颜色，默认透明 |

**特性**：
- 严格按 `render_order` 排序绘制，部件前后关系正确
- 自动跳过 `opacity <= 0` 的 drawable，隐藏部件不出现在参考图上
- 支持多套皮肤纹理替换和批量生成

---

### remap_skin_to_texture.py

将重绘好的完整角色图反向映射回 Live2D 纹理。

```bash
python remap_skin_to_texture.py <UV数据JSON> <新皮肤PNG> [输出目录] [选项]
```

| 参数 | 说明 |
|------|------|
| `UV数据JSON` | 提取的模型数据（必填） |
| `新皮肤PNG` | 重绘后的角色图（必填） |
| `输出目录` | 输出目录（可选，默认 `remapped_textures`） |
| `--mask <路径>` | 遮罩图路径：白色=修改区域，黑色=保留区域 |
| `--mask-threshold <值>` | 遮罩阈值（默认 128），>= 此值视为有效 |
| `--base-dir <目录>` | 基底纹理目录：用该目录下的纹理作为映射基底，而非原模型纹理 |
| `--drawables <列表>` | 只映射指定 drawable，逗号分隔 ID 列表（如 `'ArtMesh52,ArtMesh54'`） |
| `--exclude-drawables <列表>` | 排除指定 drawable，逗号分隔 ID 列表（与 `--mask` 配合可实现粗略圈选后排除部件） |

**特性**：
- 向量化重心坐标 + 双线性插值，避免像素锯齿
- 微小负容差消除三角形缝隙
- 遮罩在像素级精确筛选，只映射修改区域
- 自动跳过 `opacity <= 0.001` 的 drawable（避免隐藏部件被映射）
- 支持 `--drawables` 精确指定只映射哪些部件
- 支持 `--exclude-drawables` 在遮罩区域内排除特定部件
- 支持 `--base-dir` 实现多套衣服逐套合并

**粗略遮罩 + 排除部件**：
如果你只想改左半边脸，但遮罩不小心圈到了左眼和眉毛：
```bash
python remap_skin_to_texture.py data.json edited.png remapped_textures \
    --mask mask.png --exclude-drawables ArtMesh52,ArtMesh54
```
这样遮罩覆盖的区域内，ID 为 `ArtMesh52` 和 `ArtMesh54` 的部件会被跳过。

---

### compare_textures.py

对比新旧纹理的差异，生成差异图和统计报告。

```bash
python compare_textures.py <旧纹理> <新纹理> [输出目录]
```

**输出三张差异图**：

| 文件 | 说明 |
|------|------|
| `*_diff_heatmap.png` | 差异热力图，黑→红表示差异从小到大 |
| `*_diff_overlay.png` | 新纹理 + 红色高亮变化区域，最直观 |
| `*_diff_alpha.png` | 绿=新增不透明像素 / 蓝=消失的不透明像素 / 红=颜色变化 |

**终端统计**：变化像素数、变化占比（在非透明区域中）、平均差异、最大差异。

---

### draw_uv_mesh.py

在纹理图片上绘制 UV 三角形网格，用于调试 UV 映射是否正确。

```bash
python draw_uv_mesh.py <UV数据JSON> [输出目录]
```

每个 drawable 分配随机半透明颜色，绘制填充三角形 + 黑色边框，并在包围盒中心标注 `index` 编号。输出 `*_mesh.png` 和合并图 `combined_mesh.png`。

> 编号带有黑色描边和黄色文字，便于在密集纹理中识别部件。

---

## 关于 live2d-py 的修改

本项目依赖的 `live2d-py` 不是纯净的上游版本。为了能提取 UV、几何数据和可见性信息，对 C++ 层做了以下修改。

> **修改版已单独发布**：[`Drinbol/live2d-py`](https://github.com/Drinbol/live2d-py)（fork 自 EasyLive2D/live2d-py），直接使用该版本即可，无需手动打补丁。

### 修改内容

**1. Wrapper/PyModel.cpp — 向 Python 暴露新方法：**

| Python API | 返回值 | 说明 |
|-----------|--------|------|
| `GetDrawableVertices(index)` | `[(x1,y1), ...]` | 顶点坐标 |
| `GetDrawableVertexCount(index)` | `int` | 顶点数量 |
| `GetDrawableIndices(index)` | `[i0, i1, i2, ...]` | 三角形索引 |
| `GetDrawableVertexUvs(index)` | `[(u1,v1), ...]` | UV 坐标 |
| `GetDrawableTextureIndex(index)` | `int` | 纹理索引 |
| `GetDrawableRenderOrders()` | `[int, ...]` | 所有 drawable 的绘制顺序 |
| `GetDrawableOpacities()` | `[float, ...]` | 所有 drawable 的不透明度 |
| `GetDrawableParentPartIndices()` | `[int, ...]` | 所有 drawable 所属 part 索引 |

**2. Live2D/Main/src/fine-grained/Model.hpp / .cpp**
- 新增 `GetDrawableVertexUvs(int)`
- 新增 `GetDrawableTextureIndex(int)`
- 新增 `GetDrawableRenderOrders()`
- 新增 `GetDrawableOpacities()`（内部逐个调用 SDK 的 `GetDrawableOpacity`）
- 新增 `GetDrawableParentPartIndices()`（内部逐个调用 SDK 的 `GetDrawableParentPartIndex`）

**3. Live2D/Framework/src/Motion/ACubismMotion.hpp**
- 添加了一个 Hack 宏（`__ADDITIONAL_PROPERTIES__`），用于给动作回调加自定义属性。

### 为什么拉代码会报错

因为你本地有**未提交的修改**。当你执行 `git pull` 或更新子模块时，Git 发现上游这些文件也有变动，本地修改与上游冲突，因此报错。

### 关键 C++ 修复记录

| 文件 | 修复内容 | 原因 |
|------|---------|------|
| `Model.cpp` `Update()` | 末尾添加 `_model->Update()` | 无渲染器时，Core 不会重新计算 drawable opacity 和顶点位置，导致参数切换不生效 |
| `Model.cpp` `Update()` | 在 `LoadParameters()` 前由调用方执行 `SaveParameters()` | `LoadParameters()` 会覆盖用户设置的参数值，必须先保存再更新 |
| `PyModel.cpp` | 暴露 `GetDrawableRenderOrders` / `GetDrawableOpacities` / `GetDrawableParentPartIndices` | Python 层需要获取绘制顺序和可见性 |

### 建议的解决方式

**方式 A：提交本地修改（推荐）**
```bash
cd live2d-py
git add -A
git commit -m "feat: expose drawable UV/vertex/opacity/render-order to Python"
# 然后再 git pull / git submodule update
```

**方式 B：暂存后拉取**
```bash
cd live2d-py
git stash
git pull
git stash pop
# 手动解决可能的冲突
```

**方式 C：备份修改后重置**
```bash
cd live2d-py
git diff > ../live2d-py-uv-patch.diff
git checkout -- .
git pull
# 然后手动打回 patch
git apply ../live2d-py-uv-patch.diff
```

> **注意**：如果你打算给 live2d-py 上游提 PR，建议把修改整理干净后提交。目前 `PyModel.cpp` 里混入了缩进格式变更（tab→space），建议还原格式再提交。

---

## 常见问题

### Q：参考图上部件顺序错乱（头发跑到脸前面）
A：旧版本的 `render_default_pose.py` 没有按 `render_order` 排序，已修复。请重新提取 JSON（确保包含 `render_order` 字段）再渲染。

### Q：被遮挡的部件（如眼球）被意外修改了
A：使用 `--mask` 遮罩限定修改区域，或使用 `--drawables` 精确指定只修改哪些部件。如果遮罩画大了，还可以用 `--exclude-drawables` 把不想改的部件排除掉。另外请确保 JSON 是重新提取的（包含 `opacity` 字段），脚本会自动跳过隐藏的 drawable。

### Q：参数切换后参考图没有变化
A：有两个已知原因：
1. **参数名拼写错误**：请用 `python -c "import live2d.v3 as live2d; ...; print(model.GetParameterIds())"` 确认正确参数名（注意大小写）。
2. **旧版本缺少 `_model->Update()`**：如果 `live2d.pyd` 是旧编译的，参数切换不会生效。请重新编译 `live2d-py`（见上方 C++ 修复记录）。

### Q：两套衣服在反向映射后都出现了同样的修改
A：说明两套衣服在纹理上**共用 UV 区域**。请用 `draw_uv_mesh.py` 检查纹理布局。如果 UV 重叠，那是模型设计限制，无法通过脚本解决。如果 UV 不重叠，请使用"多套衣服编辑"工作流 + `--base-dir` 参数。

### Q：如何确认不同衣服的 UV 是否重叠？
A：运行 `python draw_uv_mesh.py data.json`，查看输出的 `texture_00_mesh.png`。不同颜色的半透明区域代表不同 drawable。如果两套衣服的 drawable 颜色区域在纹理上完全分离，说明 UV 不重叠。

### Q：如何快速找到某个部件的 drawable ID？
A：使用 `label_drawables.py` 在参考图上标注所有可见部件的编号和 ID：
```bash
python label_drawables.py data.json labeled.png
```
打开 `labeled.png`，红色圆点旁边会显示 `index:id`，直接定位你要修改的部件。
