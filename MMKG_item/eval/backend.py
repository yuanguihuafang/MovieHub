# -*- coding: utf-8 -*-
"""
后端服务模块 - Multi-MoE 多模态知识图谱模型后端

功能：
    - 加载预训练模型和数据集
    - 提供评估接口（支持不同数据集、评估模式）
    - 提供单样本预测接口（链接预测）
    - 读取训练日志指标
    - 获取数据集样本

设计：
    - 作为Gradio前端的后端支撑
    - 使用全局缓存避免重复加载模型和数据
    - 支持CPU/GPU灵活切换
"""

import argparse
import os
import random
import re
import sys
import json
from pathlib import Path

# 本文件：MMKG_item/eval/backend.py
_MMKG_ROOT = Path(__file__).resolve().parent.parent
# 含 MMKG_item 这一层的仓库根（Multi_MoE 内为 from MMKG_item.layers...）
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (_REPO_ROOT, _MMKG_ROOT):
    s = str(_p)
    if s not in sys.path:
        sys.path.insert(0, s)

import torch
import torch.nn.functional as F
from tqdm import tqdm

# 导入模型和数据处理模块（依赖上面对 MMKG_item 的 sys.path）
from models.Multi_MoE import Multi_MoE
from utils.data_util import load_data

# ============================================================
# 全局缓存 - 避免重复加载模型和数据
# ============================================================
_cache = {
    "model": None,  # 预训练模型实例
    "args": None,  # 模型参数配置
    "entity2id": None,  # 实体ID映射
    "relation2id": None,  # 关系ID映射
    "id2entity": None,  # ID到实体反向映射
    "id2relation": None,  # ID到关系反向映射
    "train_triples": None,  # 训练集三元组
    "valid_triples": None,  # 验证集三元组
    "test_triples": None,  # 测试集三元组
    "all_triples_set": None,  # 所有三元组集合（用于过滤）
}


# ============================================================
# 辅助函数
# ============================================================


def load_kg_eval_display_payload():
    """
    读取与前端管理后台一致的展示口径文件（single source of truth）。

    默认路径：backend/data/eval/kg_eval_display.json
    """
    p = _REPO_ROOT / "backend" / "data" / "eval" / "kg_eval_display.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def format_kg_eval_display_markdown(payload):
    """
    将 kg_eval_display.json 渲染为 Markdown（用于 Gradio 展示）。
    """
    title = (payload.get("title") or "").strip() or "知识图谱评估指标"
    task = (payload.get("task") or "").strip()
    source = (payload.get("source") or "").strip()
    metrics = payload.get("metrics") or {}
    baselines = payload.get("baselines") or []

    def _fmt_hits(v):
        try:
            if v is None:
                return "—"
            return f"{float(v) * 100:.2f}%"
        except Exception:
            return "—"

    def _fmt_num(v, nd=4):
        try:
            if v is None:
                return "—"
            return f"{float(v):.{nd}f}"
        except Exception:
            return "—"

    def _fmt_mr(v):
        try:
            if v is None:
                return "—"
            return f"{float(v):.2f}"
        except Exception:
            return "—"

    lines = [f"### 📌 {title}"]
    if task:
        lines.append(f"- **任务**：{task}")
    if source:
        lines.append(f"- **来源**：`{source}`")

    lines.append("")
    lines.append("#### 📊 测试集指标（本系统）")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("| :--- | ---: |")
    lines.append(f"| Hits@1 | {_fmt_hits(metrics.get('Hits@1'))} |")
    lines.append(f"| Hits@3 | {_fmt_hits(metrics.get('Hits@3'))} |")

    if baselines:
        lines.append("")
        lines.append("#### 📈 性能对比")
        lines.append("")
        # 只展示相对提升（pp），按 name 匹配两条基线
        try:
            h1 = float(metrics.get("Hits@1"))
            h3 = float(metrics.get("Hits@3"))
        except Exception:
            h1, h3 = None, None

        def _pp(curr, base):
            try:
                if curr is None or base is None:
                    return "—"
                return f"{(float(curr) - float(base)) * 100:.1f}pp"
            except Exception:
                return "—"

        transE = None
        ikrl = None
        for row in baselines:
            n = (row.get("name") or "").lower()
            if "transe" in n:
                transE = row
            if "ikrl" in n:
                ikrl = row

        if transE is not None:
            lines.append(
                "- 相对 **TransE（单模态）**：Hits@1 **{d1}**，Hits@3 **{d3}**".format(
                    d1=_pp(h1, transE.get("Hits@1")),
                    d3=_pp(h3, transE.get("Hits@3")),
                )
            )
        if ikrl is not None:
            lines.append(
                "- 相对 **IKRL（多模态）**：Hits@1 **{d1}**，Hits@3 **{d3}**".format(
                    d1=_pp(h1, ikrl.get("Hits@1")),
                    d3=_pp(h3, ikrl.get("Hits@3")),
                )
            )

    notes = payload.get("notes") or []
    if isinstance(notes, list) and notes:
        lines.append("")
        lines.append("#### 📝 说明")
        for n in notes:
            if n:
                lines.append(f"- {n}")

    return "\n".join(lines)


def load_all_triples(dataset):
    """
    从原始文件加载所有三元组（用于评估时过滤已知三元组）

    参数：
        dataset: 数据集名称（如'DB15K'）

    返回：
        all_triples: 三元组集合 {(head, relation, tail), ...}
    """
    all_triples = set()
    triple_files = ["train.txt", "valid.txt", "test.txt"]
    for filename in triple_files:
        filepath = _MMKG_ROOT / "datasets" / dataset / filename
        if filepath.is_file():
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) >= 3:
                        all_triples.add((parts[0], parts[1], parts[2]))
    return all_triples


def load_model_and_data(dataset="DB15K", use_cuda=False):
    """
    加载预训练模型和数据集（使用全局缓存）

    参数：
        dataset: 数据集名称，默认为'DB15K'
        use_cuda: 是否使用GPU加速，默认为False

    返回：
        True: 加载成功
        str: 错误信息（加载失败时）
    """
    global _cache

    # 如果模型已加载，直接返回（避免重复加载）
    if _cache["model"] is not None:
        return True

    try:
        # 加载数据集
        (
            entity2id,
            relation2id,
            img_features,
            text_features,
            train_data,
            valid_data,
            test_data,
        ) = load_data(dataset)
    except Exception as e:
        return f"加载数据集失败：{str(e)}"

    # 确定设备（GPU/CPU）
    device = "cuda:0" if (torch.cuda.is_available() and use_cuda) else "cpu"

    # 归一化图像和文本特征
    img_feats = F.normalize(torch.Tensor(img_features), p=2, dim=1).to(device)
    txt_feats = F.normalize(torch.Tensor(text_features), p=2, dim=1).to(device)

    # 提取三元组数据
    train_triples = (
        train_data[0] if isinstance(train_data, (list, tuple)) else train_data
    )
    valid_triples = (
        valid_data[0] if isinstance(valid_data, (list, tuple)) else valid_data
    )
    test_triples = test_data[0] if isinstance(test_data, (list, tuple)) else test_data

    # 构建模型参数
    model_args = argparse.Namespace(
        dim=256,  # 嵌入维度
        r_dim=256,  # 关系嵌入维度
        img_dim=img_feats.shape[1],  # 图像特征维度
        txt_dim=txt_feats.shape[1],  # 文本特征维度
        n_exp=3,  # MoE专家数量
        dataset=dataset,  # 数据集名称
        device=device,  # 计算设备
        entity2id=entity2id,  # 实体映射
        relation2id=relation2id,  # 关系映射
        img=img_feats,  # 图像特征
        desp=txt_feats,  # 文本特征
    )

    # 检查模型文件是否存在（相对 MMKG_item 根目录）
    model_path = _MMKG_ROOT / "checkpoint" / dataset / "trained_model.pth"
    if not model_path.is_file():
        return f"模型文件不存在：{model_path}"

    try:
        # 初始化并加载模型
        model = Multi_MoE(model_args)
        model.to(device)
        state_dict = torch.load(str(model_path), map_location=device, weights_only=True)
        model.load_state_dict(state_dict)
        model.eval()  # 设置为评估模式
    except Exception as e:
        return f"加载模型失败：{str(e)}"

    # 加载所有三元组（用于过滤）
    all_triples_set = load_all_triples(dataset)

    # 更新全局缓存
    _cache.update(
        {
            "model": model,
            "args": model_args,
            "entity2id": entity2id,
            "relation2id": relation2id,
            "id2entity": {v: k for k, v in entity2id.items()},
            "id2relation": {v: k for k, v in relation2id.items()},
            "train_triples": train_triples,
            "valid_triples": valid_triples,
            "test_triples": test_triples,
            "all_triples_set": all_triples_set,
        }
    )
    return True


def read_metrics_from_log():
    """
    从训练日志文件读取最终的测试指标

    返回：
        dict: 包含Hits@1/3/10/100、MR、MRR等指标
        None: 日志文件不存在或解析失败
    """
    log_path = _MMKG_ROOT / "log" / "log_new.txt"
    if not log_path.is_file():
        return None

    with open(log_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 使用正则表达式提取指标
    pattern = r"Test set results:.*?test_Hits@100:\s*([\d.]+).*?test_Hits@10:\s*([\d.]+).*?test_Hits@3:\s*([\d.]+).*?test_Hits@1:\s*([\d.]+).*?test_MR:\s*([\d.]+).*?test_MRR:\s*([\d.]+)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        h100, h10, h3, h1, mr, mrr = match.groups()
        return {
            "Hits@1": float(h1),
            "Hits@3": float(h3),
            "Hits@10": float(h10),
            "Hits@100": float(h100),
            "MR": float(mr),
            "MRR": float(mrr),
            "Total": "完整测试集",
            "source": "MMKG_item/log/log_new.txt (2000 epochs)",
        }
    return None


def get_random_samples(dataset_name="valid_triples", n=8):
    """
    从指定数据集随机抽取样本用于展示

    参数：
        dataset_name: 数据集名称（'valid_triples' 或 'test_triples'）
        n: 抽取样本数量

    返回：
        str: Markdown格式的样本表格
    """
    triples = _cache.get(dataset_name)
    if triples is None:
        return "数据集尚未加载。"
    if len(triples) == 0:
        return "数据集为空。"

    # 随机抽取样本
    samples = random.sample(list(triples), min(n, len(triples)))
    id2entity = _cache["id2entity"]
    id2relation = _cache["id2relation"]

    # 构建Markdown表格
    lines = [
        "| 头实体 | 关系 | 尾实体 |",
        "| :----- | :--- | :----- |",
    ]

    for h_id, r_id, t_id in samples:
        # 将URI转换为短名称便于显示
        h = id2entity[h_id].rstrip(">").rsplit("/", 1)[-1]
        r = id2relation[r_id].rstrip(">").rsplit("/", 1)[-1]
        t = id2entity[t_id].rstrip(">").rsplit("/", 1)[-1]
        lines.append(f"| {h} | {r} | {t} |")

    return "\n".join(lines)


def evaluate_triple(
    model,
    head_id,
    rel_id,
    tail_id,
    entity2id,
    relation2id,
    all_triples_set,
    model_args,
    mode="tail",
):
    """
    评估单个三元组的预测排名（链接预测任务）

    参数：
        model: 预训练模型
        head_id: 头实体ID
        rel_id: 关系ID
        tail_id: 尾实体ID
        entity2id: 实体ID映射
        relation2id: 关系ID映射
        all_triples_set: 所有已知三元组集合（用于过滤）
        model_args: 模型参数
        mode: 预测模式，'tail'预测尾实体，'head'预测头实体

    返回：
        int: 真实尾实体/头实体的排名（排名越低越好）
    """
    num_entities = len(entity2id)
    id2entity = {v: k for k, v in entity2id.items()}
    id2relation = {v: k for k, v in relation2id.items()}
    device = model_args.device

    if mode == "tail":
        # 预测尾实体：给定(头实体, 关系)，预测尾实体
        batch = torch.LongTensor([[head_id, rel_id, 0]]).to(device)
        with torch.no_grad():
            output, _ = model.forward(batch, None)

        # 四分支预测取平均
        pred_avg = (output[0] + output[1] + output[2] + output[3]) / 4.0

        # 获取URI用于过滤已知三元组
        head_uri = id2entity[head_id]
        rel_uri = id2relation[rel_id]

        # 过滤已知三元组（将已知尾实体的分数设为负无穷）
        for e_id in range(num_entities):
            e_uri = id2entity[e_id]
            if (head_uri, rel_uri, e_uri) in all_triples_set:
                pred_avg[0, e_id] = -float("inf")

        # 将真实尾实体分数也设为负无穷（模拟不知道答案的情况）
        pred_avg[0, tail_id] = -float("inf")

        # 重新获取真实尾实体的分数（排除在过滤之外）
        batch2 = torch.LongTensor([[head_id, rel_id, tail_id]]).to(device)
        with torch.no_grad():
            output2, _ = model.forward(batch2, None)
        correct_score = (
            output2[0][0, tail_id]
            + output2[1][0, tail_id]
            + output2[2][0, tail_id]
            + output2[3][0, tail_id]
        ) / 4.0
        pred_avg[0, tail_id] = correct_score

        # 计算真实尾实体的排名
        rank = (pred_avg[0].argsort(descending=True) == tail_id).nonzero(as_tuple=True)[
            0
        ].item() + 1
        return rank

    else:  # mode == "head"
        # 预测头实体：给定(关系, 尾实体)，预测头实体
        # 使用逆关系：tail, -relation -> head
        ranks = []
        for h_id in range(num_entities):
            batch = torch.LongTensor([[h_id, rel_id + len(relation2id), 0]]).to(device)
            with torch.no_grad():
                output, _ = model.forward(batch, None)
            pred_avg = (output[0] + output[1] + output[2] + output[3]) / 4.0
            ranks.append(pred_avg.squeeze(0)[tail_id].item())

        scores = torch.tensor(ranks)
        tail_uri = id2entity[tail_id]
        rel_uri = id2relation[rel_id]

        # 过滤已知三元组
        for h_id in range(num_entities):
            h_uri = id2entity[h_id]
            if (h_uri, rel_uri, tail_uri) in all_triples_set:
                scores[h_id] = -float("inf")
        scores[head_id] = ranks[head_id]

        # 计算排名
        rank = (scores.argsort(descending=True) == head_id).nonzero(as_tuple=True)[
            0
        ].item() + 1
        return rank


def quick_evaluate(test_triples, use_cuda=False, max_samples=100, eval_mode="tail"):
    """
    快速评估：在测试集上评估模型性能

    参数：
        test_triples: 测试三元组列表
        use_cuda: 是否使用GPU
        max_samples: 最多评估样本数
        eval_mode: 评估模式 ('tail'或'head')

    返回：
        dict: 评估指标 {MRR, Hits@1, Hits@3, Hits@10, Total}
    """
    if _cache["model"] is None:
        return {"error": "模型未加载"}
    if test_triples is None or len(test_triples) == 0:
        return {"error": "测试集为空"}

    model = _cache["model"]
    model_args = _cache["args"]

    # 切换设备
    if use_cuda and torch.cuda.is_available():
        model_args.device = "cuda:0"
        model.to("cuda:0")
    else:
        model_args.device = "cpu"
        model.to("cpu")

    entity2id = _cache["entity2id"]
    relation2id = _cache["relation2id"]
    all_triples_set = _cache["all_triples_set"]
    id2entity = _cache["id2entity"]
    id2relation = _cache["id2relation"]

    # 采样评估
    sample_triples = test_triples[:max_samples]
    total = len(sample_triples)

    ranks = []
    for h_id, r_id, t_id in tqdm(sample_triples, desc=f"评估中 ({eval_mode})"):
        try:
            rank = evaluate_triple(
                model,
                h_id,
                r_id,
                t_id,
                entity2id,
                relation2id,
                all_triples_set,
                model_args,
                mode=eval_mode,
            )
            ranks.append(rank)
        except Exception as e:
            print(f"Error on triple ({h_id}, {r_id}, {t_id}): {e}")
            continue

    if len(ranks) == 0:
        return {"MRR": 0.0, "Hits@1": 0.0, "Hits@3": 0.0, "Hits@10": 0.0, "Total": 0}

    # 计算评估指标
    mrr = sum(1.0 / r for r in ranks) / len(ranks)
    hits1 = sum(1 for r in ranks if r <= 1) / len(ranks)
    hits3 = sum(1 for r in ranks if r <= 3) / len(ranks)
    hits10 = sum(1 for r in ranks if r <= 10) / len(ranks)

    return {
        "MRR": round(mrr, 4),
        "Hits@1": round(hits1, 4),
        "Hits@3": round(hits3, 4),
        "Hits@10": round(hits10, 4),
        "Total": len(ranks),
    }


def evaluate_quick(test_file, use_cuda=False, max_samples=100, eval_mode="tail"):
    """
    统一快速评估接口（前端调用）

    参数：
        test_file: 测试文件名 ('valid.txt' 或 'test.txt')
        use_cuda: 是否使用GPU
        max_samples: 最大样本数
        eval_mode: 评估模式

    返回：
        dict: 评估指标
    """
    # 映射文件名到缓存键
    file_to_cache_key = {"valid.txt": "valid_triples", "test.txt": "test_triples"}
    cache_key = file_to_cache_key.get(test_file)
    if cache_key is None:
        return {"error": f"无效的测试文件: {test_file}"}

    test_triples = _cache.get(cache_key)
    if test_triples is None:
        return {"error": "数据集未加载，请先加载模型"}

    return quick_evaluate(test_triples, use_cuda, max_samples, eval_mode)


def predict_tail(head_entity, relation, topk=10):
    """
    单样本预测：根据头实体和关系预测尾实体（链接预测）

    参数：
        head_entity: 头实体名称（支持URI或短名）
        relation: 关系名称（支持URI或短名）
        topk: 返回Top-K个候选尾实体

    返回：
        dict: 预测结果 {success: True, results: [{rank, entity, score}, ...]}
              或 {error: 错误信息}
    """
    model = _cache["model"]
    model_args = _cache["args"]
    entity2id = _cache["entity2id"]
    relation2id = _cache["relation2id"]
    id2entity = _cache["id2entity"]
    all_triples_set = _cache["all_triples_set"]
    device = model_args.device

    # 查找头实体（支持URI或短名模糊匹配）
    head_uri = None
    if head_entity in entity2id:
        head_uri = head_entity
    else:
        for uri in entity2id.keys():
            # 尝试匹配短名称
            if uri.rstrip(">").rsplit("/", 1)[-1] == head_entity:
                head_uri = uri
                break
        if head_uri is None:
            return {"error": f"头实体 '{head_entity}' 不存在"}

    # 查找关系（支持URI或短名模糊匹配）
    rel_uri = None
    if relation in relation2id:
        rel_uri = relation
    else:
        for uri in relation2id.keys():
            if uri.rstrip(">").rsplit("/", 1)[-1] == relation:
                rel_uri = uri
                break
        if rel_uri is None:
            return {"error": f"关系 '{relation}' 不存在"}

    head_id = entity2id[head_uri]
    rel_id = relation2id[rel_uri]

    # 前向预测
    batch = torch.LongTensor([[head_id, rel_id, 0]]).to(device)
    with torch.no_grad():
        output, _ = model.forward(batch, None)
    pred_avg = (output[0] + output[1] + output[2] + output[3]) / 4.0

    # 过滤已知三元组
    num_entities = len(entity2id)
    for e_id in range(num_entities):
        e_uri = id2entity[e_id]
        if (head_uri, rel_uri, e_uri) in all_triples_set:
            pred_avg[0, e_id] = -float("inf")

    # 获取Top-K预测
    k = min(topk, num_entities)
    topk_scores, topk_indices = torch.topk(pred_avg, k=k, dim=1)
    topk_scores = topk_scores.squeeze(0).tolist()
    topk_indices = topk_indices.squeeze(0).tolist()

    # 构建结果
    results = []
    for rank, (idx, score) in enumerate(zip(topk_indices, topk_scores), start=1):
        full_uri = id2entity[idx]
        short_name = full_uri.rstrip(">").rsplit("/", 1)[-1]
        results.append(
            {
                "rank": rank,
                "entity": short_name,
                "score": round(score, 4),
            }
        )

    return {"success": True, "results": results}


def get_metrics():
    """
    获取模型性能指标

    返回：
        dict: 从日志文件读取的评估指标
    """
    return read_metrics_from_log()


def get_valid_samples():
    """
    获取验证集随机样本

    返回：
        str: Markdown格式的样本表格
    """
    return get_random_samples("valid_triples", 10)


def is_model_loaded():
    """
    检查模型是否已加载

    返回：
        bool: 模型是否已加载
    """
    return _cache["model"] is not None


def get_model_info():
    """
    获取模型信息（实体/关系数量）

    返回：
        dict: {entity_count, relation_count}
        None: 模型未加载
    """
    if _cache["model"] is None:
        return None
    return {
        "entity_count": len(_cache["entity2id"]),
        "relation_count": len(_cache["relation2id"]),
    }
