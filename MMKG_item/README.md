# MMKG_item（Multi-MoE 多模态知识图谱补全）

本目录是 MovieHub 仓库中的**模型训练与评估子项目**，用于在 **MMKG / DB15K** 数据集上训练多模态知识图谱补全模型（默认：`Multi_MoE`），并提供一个 Gradio 演示界面用于快速评估与单样本推理。

---

## 目录结构

```
MMKG_item/
├── train.py                      # 训练入口（默认训练 Multi_MoE）
├── models/
│   ├── Multi_MoE.py               # 主模型（多模态 Mixture-of-Experts）
│   ├── model.py                   # BaseModel / loss / metrics 格式化等
│   └── modules.py                 # 模型通用组件
├── layers/
│   ├── layer1_moe.py              # MoE 适配层（专家+门控）
│   ├── layer2_fuse.py             # 多模态融合层
│   └── layer.py                   # 参考代码层（学习用）
├── utils/
│   ├── data_util.py               # 数据读取/划分/邻接构建/特征加载
│   ├── data_loader.py             # 训练数据封装 + 评估(MRR/Hits@K)
│   └── log_eval.py                # 日志/评估辅助
├── datasets/
│   ├── DB15K/                     # 训练用数据（本项目格式：train/valid/test + 映射 + 特征）
│   └── nle-ml-mmkb-71aed5e/       # MMKG 官方组件文件（EntityTriples/Numerical/SameAs/ImageIndex）
├── checkpoint/
│   └── DB15K/trained_model.pth    # 训练输出（或用于演示加载）
├── log/
│   └── log_new.txt                # 训练日志（演示界面会读取末行指标）
└── eval/
    ├── app.py                     # Gradio UI（可视化/快速评估/单样本预测）
    └── backend.py                 # Gradio 后端逻辑（加载模型、过滤评估等）
```

---

## 环境与依赖

建议使用 Python 3.10+。

在仓库根目录安装依赖（复用根目录 `requirements.txt`）：

```bash
pip install -r requirements.txt
```

如需 GPU（可选）：

```bash
# 以 CUDA 11.8 为例，按你的 CUDA 版本选择
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

---

## 数据准备（MMKG 官方组件 → 本项目训练格式）

### 1) 放置 MMKG 官方组件文件（数据来源）

你已经下载的目录示例：

```
MMKG_item/datasets/nle-ml-mmkb-71aed5e/DB15K/
  DB15K_EntityTriples.txt
  DB15K_NumericalTriples.txt
  DB15K_SameAsLink.txt
  DB15K_ImageIndex.txt
```

本项目的主训练流程（`train.py`）默认使用的是 `MMKG_item/datasets/DB15K/` 下的训练格式文件（见下一步）。

### 2) 生成训练/验证/测试划分与映射文件（结构三元组）

`utils/data_util.py` 中提供了随机划分逻辑（90/5/5）与映射生成逻辑：

- 从 `<dataset>_EntityTriples.txt` 生成：
  - `train.txt` / `valid.txt` / `test.txt`
  - `entity2id.txt` / `relation2id.txt`

你可以用任意方式生成，但要满足 `load_data()` 的读取约定：

```
MMKG_item/datasets/DB15K/
  train.txt
  valid.txt
  test.txt
  entity2id.txt
  relation2id.txt
```

> 说明：当前已经存在上述文件（至少结构数据部分），因此一般不需要重新划分。

### 3) 准备多模态特征文件（必须）

`utils/data_util.load_data()` 会读取：

- `MMKG_item/datasets/DB15K/img_features.pth`
- `MMKG_item/datasets/DB15K/text_features.pth`

可选（当你调用 `load_more_data(..., numeric=True)` 才需要）：

- `MMKG_item/datasets/DB15K/numeric_features.pth`

如果上述 `.pth` 不存在，训练/演示都会报错。请确保这些特征与你的 `entity2id.txt` **顺序对齐**（第 \(i\) 行实体对应特征矩阵第 \(i\) 行）。

> 备注：`data_util.py` 里有 `write_img_vec()`（从 `<dataset>_ImageData.h5` 读取并写 `img_features.pkl`）的旧路径，但当前训练/演示实际读的是 `.pth`。

---

## 训练（Multi_MoE）

在仓库根目录运行（推荐，import 路径更稳）：

```bash
python MMKG_item/train.py
```

常用参数（都在 `train.py` 的 `parse_args()` 默认值里）：

- `--dataset`：默认 `DB15K`
- `--cuda`：GPU id；用 CPU 设为 `-1`
- `--epochs`：训练轮数（默认 2000）
- `--batch_size`：批大小（默认 1024）
- `--decoder_save_model`：模型保存路径（默认 `./checkpoint/DB15K/trained_model.pth`，相对运行目录）

示例（CPU）：

```bash
python MMKG_item/train.py --cuda -1
```

训练结束后你应能看到：

- `MMKG_item/checkpoint/DB15K/trained_model.pth`（或你自定义的保存路径）
- `MMKG_item/log/log_new.txt`（若你的训练脚本/日志逻辑开启写入；演示界面会读取这里的末行指标）

---

## 评估与演示（Gradio）

启动演示界面：

```bash
python MMKG_item/eval/app.py
```

默认访问：

- `http://localhost:7860`

演示界面会：

- 加载数据：`MMKG_item/datasets/DB15K/`
- 加载模型：`MMKG_item/checkpoint/DB15K/trained_model.pth`
- 从日志读取测试指标：`MMKG_item/log/log_new.txt`

如果提示“模型文件不存在”，先完成训练或把已有权重放到对应路径。

---

## 数据处理与训练细节

本项目的数据与训练流程：

- **数据加载与划分**：`utils/data_util.py`
  - `dataset_split()`：从 `DB15K_EntityTriples.txt` 随机划分 90/5/5 得到 `train/valid/test`
  - `write_index_dict()`：生成 `entity2id / relation2id`
  - `get_adj()`：读取 split 三元组并构建邻接表示（用于模型结构分支的图信息输入）
  - `load_data()`：加载结构数据 + 图像/文本特征（`.pth`）
- **训练样本组织**：`utils/data_loader.py`（`ConvECorpus`）
  - 为每个关系自动添加 `*_reverse` 逆关系，实现**头/尾双向预测**
  - 将同一 `(head, relation)` 对应的所有正确 `tail` 作为**多标签（multi-hot）监督**
  - 评估输出常用指标：**MRR、Hits@K、MR**
- **训练入口**：`train.py`
  - 模型：`models/Multi_MoE.py`（结构/图像/文本/融合四分支 + MoE 门控）
  - 特征归一化：对图像/文本特征做 L2 normalize

---

## 基线模型对比

`models/model.py` 中实现了 TransE 和 IKRL 两个基线模型。在 `train.py` 中手动切换注释即可：

```python
# 选择模型：取消注释对应行即可切换
model = Multi_MoE(args)
# model = BaselineWrapper(TransE(args))
# model = BaselineWrapper(IKRL(args))
```

`layers/layer.py` 保留了部分参考代码，当前主流程不会调用。

---

## 常见问题

### 1) 找不到 `img_features.pth` / `text_features.pth`

说明你的多模态特征文件未准备好或路径不对。请确认文件存在于：

`MMKG_item/datasets/DB15K/`

并且行顺序与 `entity2id.txt` 对齐。

### 2) GPU 不可用/想用 CPU

```bash
python MMKG_item/train.py --cuda -1
```

### 3) 演示界面提示模型权重不存在

请确认权重文件存在：

`MMKG_item/checkpoint/DB15K/trained_model.pth`

或先运行训练脚本生成。

---

## 引用与数据来源

- MMKG 论文：**MMKG: Multi-Modal Knowledge Graphs**（arXiv:1903.05485）
- MMKG 官方数据组件（sameAs / numerical / image index 等）来自 `nle-ml/mmkb` 发布资源（详见其 README 与 License）。