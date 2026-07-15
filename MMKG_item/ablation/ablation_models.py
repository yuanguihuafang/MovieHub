"""
消融实验模型变体

基于 Multi_MoE 的消融模型，通过开关控制各模态和融合分支的启用/禁用，
用于量化每个组件对最终性能的贡献。

实验设计：
    A. 模态消融 — StructOnly / TextOnly / Full
    B. MoE 专家数消融 — 1 专家 vs 3 专家
    C. 单分支评估 — 分别评估四个分支的贡献
"""
import torch
import torch.nn as nn
from MMKG_item.models.Multi_MoE import Multi_MoE


class Multi_MoE_Ablation(Multi_MoE):
    """
    Multi-MoE 消融变体

    参数：
        use_image: 是否启用图像模态
        use_text: 是否启用文本模态
        use_fusion: 是否启用融合分支（pred_mm）

    行为：
        - 禁用的模态用零向量替代其 MoE 输出
        - 禁用的分支不计入损失
        - 评估时只返回活跃分支的预测
    """

    def __init__(self, args, use_image=True, use_text=True, use_fusion=True):
        super(Multi_MoE_Ablation, self).__init__(args)

        self.use_image = use_image
        self.use_text = use_text
        self.use_fusion = use_fusion

    def forward(self, batch_inputs, adj):
        """
        前向传播（消融版）

        禁用的模态用零向量替代，确保模型结构不变、训练正常进行，
        只是被禁用的分支无法学到有效信息。
        """
        head = batch_inputs[:, 0]
        relation = batch_inputs[:, 1]

        # 结构嵌入（始终启用）
        stru_head = self.entity_embeddings(head)
        e_embed, disen_str, atten_s = self.structure_moe(stru_head)

        # 图像嵌入（可控）
        if self.use_image:
            img_head = self.img_entity_embeddings(head)
            e_img_embed, disen_img, atten_i = self.visual_moe(img_head)
        else:
            e_img_embed = torch.zeros_like(e_embed)
            disen_img = torch.zeros_like(disen_str)
            atten_i = torch.zeros(e_embed.size(0), self.visual_moe.n_exps, device=self.device)

        # 文本嵌入（可控）
        if self.use_text:
            txt_head = self.txt_entity_embeddings(head)
            e_txt_embed, disen_txt, atten_t = self.text_moe(txt_head)
        else:
            e_txt_embed = torch.zeros_like(e_embed)
            disen_txt = torch.zeros_like(disen_str)
            atten_t = torch.zeros(e_embed.size(0), self.text_moe.n_exps, device=self.device)

        # 关系嵌入
        r_embed = self.relation_embeddings(relation)
        r_img_embed = r_embed if self.use_image else torch.zeros_like(r_embed)
        r_txt_embed = r_embed if self.use_text else torch.zeros_like(r_embed)

        # 多模态融合（可控）
        if self.use_fusion:
            e_mm_embed, attn_f = self.fuse_e(e_embed, e_img_embed, e_txt_embed)
            r_mm_embed, _ = self.fuse_r(r_embed, r_img_embed, r_txt_embed)
        else:
            e_mm_embed = torch.zeros_like(e_embed)
            r_mm_embed = torch.zeros_like(r_embed)
            attn_f = torch.zeros(e_embed.size(0), 3, device=self.device)

        # 四分支预测分数
        pred_s = e_embed * r_embed
        pred_i = e_img_embed * r_img_embed
        pred_d = e_txt_embed * r_txt_embed
        pred_mm = e_mm_embed * r_mm_embed

        # 与所有实体计算得分
        all_s = self.entity_embeddings.weight
        all_v = self.img_entity_embeddings.weight
        all_t = self.txt_entity_embeddings.weight
        all_f, _ = self.fuse_e(all_s, all_v, all_t)

        pred_s = torch.sigmoid(torch.mm(pred_s, all_s.t()))
        pred_i = torch.sigmoid(torch.mm(pred_i, all_v.t()))
        pred_d = torch.sigmoid(torch.mm(pred_d, all_t.t()))
        pred_mm = torch.sigmoid(torch.mm(pred_mm, all_f.t()))

        if not self.training:
            return [pred_s, pred_i, pred_d, pred_mm], [atten_s, atten_i, atten_t, attn_f]
        else:
            return [pred_s, pred_i, pred_d, pred_mm], [disen_str, disen_img, disen_txt]

    def loss_func(self, output, target):
        """
        加权损失函数 — 禁用的分支不计入损失
        """
        loss = 0.0
        active_masks = [True, self.use_image, self.use_text, self.use_fusion]
        for pred, active in zip(output, active_masks):
            if active:
                loss = loss + self.bceloss(pred, target)
        return loss


# ============================================================
# 预定义消融配置
# ============================================================

ABLATION_CONFIGS = {
    # ---- A. 模态消融（最小必要组）----
    "StructOnly": {"use_image": False, "use_text": False, "use_fusion": False,
                   "group": "modality", "desc": "仅结构嵌入（基线）"},
    "TextOnly":   {"use_image": False, "use_text": True,  "use_fusion": False,
                   "group": "modality", "desc": "仅文本嵌入"},
    "Full":       {"use_image": True,  "use_text": True,  "use_fusion": True,
                   "group": "modality", "desc": "完整模型 S+I+T+F"},

    # ---- B. MoE 专家数消融（完整模型，改变 n_exp）----
    "MoE_1expert":  {"use_image": True, "use_text": True, "use_fusion": True,
                     "n_exp": 1, "group": "moe", "desc": "1 个专家（无 MoE）"},
    "MoE_3experts": {"use_image": True, "use_text": True, "use_fusion": True,
                     "n_exp": 3, "group": "moe", "desc": "3 个专家（默认）"},

    # ---- C. 单分支评估（使用 Full 模型，评估时拆分）----
    "Branch_struct":  {"use_image": True, "use_text": True, "use_fusion": True,
                       "eval_branch": 0, "group": "branch", "desc": "仅结构分支 pred_s"},
    "Branch_image":   {"use_image": True, "use_text": True, "use_fusion": True,
                       "eval_branch": 1, "group": "branch", "desc": "仅图像分支 pred_i"},
    "Branch_text":    {"use_image": True, "use_text": True, "use_fusion": True,
                       "eval_branch": 2, "group": "branch", "desc": "仅文本分支 pred_d"},
    "Branch_fusion":  {"use_image": True, "use_text": True, "use_fusion": True,
                       "eval_branch": 3, "group": "branch", "desc": "仅融合分支 pred_mm"},
    "Branch_avg":     {"use_image": True, "use_text": True, "use_fusion": True,
                       "eval_branch": -1, "group": "branch", "desc": "四分支平均（完整逻辑）"},
}
