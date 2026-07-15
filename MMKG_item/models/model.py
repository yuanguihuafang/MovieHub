"""
模型定义模块 - 基础模型类和基线模型

包含：
    - BaseModel: 所有模型的基类，提供通用方法
    - TransE: 经典单模态知识图谱嵌入（h + r ≈ t）
    - IKRL: 多模态知识图谱嵌入（结构 + 图像）

这些是本项目的基线模型，用于与 Multi-MoE 进行对比实验。
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# 基础模型类
class BaseModel(nn.Module):
    """
    所有知识图谱模型的基类

    提供：
        - 设备管理
        - 指标格式化
        - 指标初始化
    """
    def __init__(self, args):
        super(BaseModel, self).__init__()
        self.device = args.device

    @staticmethod
    def format_metrics(metrics, split):
        return " ".join(
            [
                "{}_{}: {:.4f}".format(split, metric_name, metric_val)
                for metric_name, metric_val in metrics.items()
            ]
        )

    @staticmethod
    def has_improved(m1, m2):
        return (m1["Mean Rank"] > m2["Mean Rank"]) or (
            m1["Mean Reciprocal Rank"] < m2["Mean Reciprocal Rank"]
        )

    @staticmethod
    def init_metric_dict():
        return {
            "Hits@100": -1,
            "Hits@10": -1,
            "Hits@3": -1,
            "Hits@1": -1,
            "MR": 100000,
            "MRR": -1,
        }


# ============================================================
# TransE — Translating Embeddings for Modeling Multi-relational Data
# ============================================================

class TransE(BaseModel):
    """
    TransE 基线模型

    评分函数: score = -||h + r - t||_2
    只使用结构嵌入，是单模态基线。

    参考: Bordes et al., Translating Embeddings for Modeling Multi-relational Data, NeurIPS 2013
    """

    def __init__(self, args):
        super(TransE, self).__init__(args)
        self.dim = args.dim

        self.entity_embeddings = nn.Embedding(len(args.entity2id), args.dim)
        nn.init.xavier_normal_(self.entity_embeddings.weight)

        self.relation_embeddings = nn.Embedding(2 * len(args.relation2id), args.dim)
        nn.init.xavier_normal_(self.relation_embeddings.weight)

        self.bceloss = nn.BCELoss()

    def forward(self, batch_inputs, adj=None):
        head = batch_inputs[:, 0]
        relation = batch_inputs[:, 1]

        h = self.entity_embeddings(head)
        r = self.relation_embeddings(relation)
        t_all = self.entity_embeddings.weight

        hr = h + r
        dist = torch.cdist(hr, t_all, p=2)
        pred = torch.sigmoid(-dist)

        return pred

    def loss_func(self, output, target):
        return self.bceloss(output, target)


# ============================================================
# IKRL — Image-embodied Knowledge Representation Learning
# ============================================================

class IKRL(BaseModel):
    """
    IKRL 基线模型 — 多模态知识图谱嵌入

    结合结构嵌入和图像嵌入，通过可学习权重融合后进行链接预测。

    评分函数:
        pred_s = sigmoid(-||h_s + r - t_s||)   结构分支
        pred_i = sigmoid(-||h_i + r - t_i||)   图像分支
        pred   = α * pred_s + (1-α) * pred_i    加权融合

    参考: Xie et al., Image-embodied Knowledge Representation Learning, IJCAI 2017
    """

    def __init__(self, args):
        super(IKRL, self).__init__(args)
        self.dim = args.dim
        self.device = args.device

        # 结构嵌入
        self.entity_embeddings = nn.Embedding(len(args.entity2id), args.dim)
        nn.init.xavier_normal_(self.entity_embeddings.weight)

        self.relation_embeddings = nn.Embedding(2 * len(args.relation2id), args.dim)
        nn.init.xavier_normal_(self.relation_embeddings.weight)

        # 图像嵌入（预提取特征，可微调）
        if args.dataset == "DB15K":
            img_pool = nn.AvgPool2d(4, stride=4)
            img = img_pool(args.img.to(self.device).view(-1, 64, 64))
            img = img.view(img.size(0), -1)
        self.img_entity_embeddings = nn.Embedding.from_pretrained(img, freeze=False)
        img_dim = self.img_entity_embeddings.weight.shape[1]

        # 图像→结构空间投影（对齐维度）
        self.img_proj = nn.Linear(img_dim, self.dim)

        # 跨模态融合权重（可学习）
        self.alpha = nn.Parameter(torch.tensor(0.5))

        self.bceloss = nn.BCELoss()

    def forward(self, batch_inputs, adj=None):
        head = batch_inputs[:, 0]
        relation = batch_inputs[:, 1]

        # 结构嵌入
        h_s = self.entity_embeddings(head)
        r = self.relation_embeddings(relation)
        t_s_all = self.entity_embeddings.weight

        # 图像嵌入（投影到结构空间）
        h_i = self.img_proj(self.img_entity_embeddings(head))
        t_i_all = self.img_proj(self.img_entity_embeddings.weight)

        # 结构分支
        hr_s = h_s + r
        dist_s = torch.cdist(hr_s, t_s_all, p=2)
        pred_s = torch.sigmoid(-dist_s)

        # 图像分支
        hr_i = h_i + r
        dist_i = torch.cdist(hr_i, t_i_all, p=2)
        pred_i = torch.sigmoid(-dist_i)

        # 跨模态融合
        alpha = torch.sigmoid(self.alpha)
        pred = alpha * pred_s + (1 - alpha) * pred_i

        return pred

    def loss_func(self, output, target):
        return self.bceloss(output, target)


# ============================================================
# BaselineWrapper — 适配基线模型到 Multi_MoE 的接口
# ============================================================

class BaselineWrapper(nn.Module):
    """
    将基线模型（TransE/IKRL）适配为 Multi_MoE 的接口格式。

    get_validation_pred 期望 forward 返回
    ([pred_s, pred_i, pred_d, pred_mm], [atten_s, atten_i, atten_t, atten_mm])
    此包装器将单 pred 复制 4 份，使四分支平均逻辑可复用。
    """

    def __init__(self, base_model):
        super().__init__()
        self.model = base_model

    def forward(self, batch_inputs, adj=None):
        pred = self.model(batch_inputs, adj)
        return [pred, pred, pred, pred], [None, None, None, None]

    def loss_func(self, output, target):
        return self.model.loss_func(output[0], target)

    def init_metric_dict(self):
        return self.model.init_metric_dict()

    def format_metrics(self, metrics, split):
        return self.model.format_metrics(metrics, split)
