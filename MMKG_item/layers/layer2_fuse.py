"""
多模态融合层模块 - 融合结构、图像、文本三种模态

包含：
    - ModalFusionLayer: 多模态融合层

原理：
    - 将三个不同模态的嵌入向量融合为一个统一的表示
    - 使用注意力机制自适应学习各模态的重要性权重
    - 支持multi个融合路径的叠加

用途：
    - 实体融合：将结构嵌入、图像嵌入、文本嵌入融合
    - 关系融合：同样处理关系的三模态表示
"""

import torch
import torch.nn as nn

class ModalFusionLayer(nn.Module):
    """
    多模态融合层 - 融合三个模态的嵌入表示

    原理：
        - 为每个模态创建独立的变换网络
        - 使用注意力机制计算各模态的重要性权重
        - 加权求和得到融合表示

    结构：
        - 3 * multi 个变换层（每个模态multi个）
        - 1个注意力层

    公式：
        attn_weights = softmax(Linear(modal1 || modal2 || modal3))
        fused = Σ(attn_i * modal_i)
    """

    def __init__(self, in_dim, out_dim, multi, img_dim, txt_dim):
        """
        初始化多模态融合层

        参数：
            in_dim: 输入维度（三种模态的原始维度）
            out_dim: 输出维度（融合后的目标维度）
            multi: 融合路径数量（每个模态使用multi个变换层叠加）
            img_dim: 图像模态的实际维度
            txt_dim: 文本模态的实际维度
        """
        super(ModalFusionLayer, self).__init__()

        self.in_dim = in_dim
        self.out_dim = out_dim
        self.multi = multi
        self.img_dim = img_dim
        self.text_dim = txt_dim

        # ========== 为每个模态创建变换层 ==========
        # 注意：self.multi的含义是叠加多层MLP，与多模态无关

        # 模态1（结构）的变换层
        modal1 = []
        for _ in range(self.multi):
            do = nn.Dropout(p=0.2)
            lin = nn.Linear(in_dim, out_dim)
            modal1.append(nn.Sequential(do, lin, nn.ReLU()))
        self.modal1_layers = nn.ModuleList(modal1)

        # 模态2（图像）的变换层
        # 输入维度可能与结构不同（img_dim）
        modal2 = []
        for _ in range(self.multi):
            do = nn.Dropout(p=0.2)
            lin = nn.Linear(self.img_dim, out_dim)
            modal2.append(nn.Sequential(do, lin, nn.ReLU()))
        self.modal2_layers = nn.ModuleList(modal2)

        # 模态3（文本）的变换层
        modal3 = []
        for _ in range(self.multi):
            do = nn.Dropout(p=0.2)
            lin = nn.Linear(self.text_dim, out_dim)
            modal3.append(nn.Sequential(do, lin, nn.ReLU()))
        self.modal3_layers = nn.ModuleList(modal3)

        # ========== 注意力机制 ==========
        # 用于计算每个模态的重要性权重
        # 输入：三个模态的变换结果拼接 [batch, 3, out_dim]
        # 输出：注意力分数 [batch, 3]
        self.ent_attn = nn.Linear(self.out_dim, 1, bias=False)
        self.ent_attn.requires_grad_(True)

    def forward(self, modal1_emb, modal2_emb, modal3_emb):
        """
        前向传播：融合三个模态的嵌入

        参数：
            modal1_emb: 结构嵌入 [batch, in_dim]
            modal2_emb: 图像嵌入 [batch, img_dim]
            modal3_emb: 文本嵌入 [batch, txt_dim]

        返回：
            fused: 融合后的嵌入 [batch, out_dim]
            attention_weights: 各模态的注意力权重 [batch, 3]
        """
        batch_size = modal1_emb.size(0)

        # 存储每条融合路径的结果
        x_mm = []

        # 遍历multi条融合路径
        for i in range(self.multi):
            # Step 1: 各模态分别变换到统一维度
            x_modal1 = self.modal1_layers[i](modal1_emb)  # [batch, out_dim]
            x_modal2 = self.modal2_layers[i](modal2_emb)  # [batch, out_dim]
            x_modal3 = self.modal3_layers[i](modal3_emb)  # [batch, out_dim]

            # Step 2: 沿dim=1堆叠三个模态
            # x_stack: [batch, 3, out_dim]
            x_stack = torch.stack((x_modal1, x_modal2, x_modal3), dim=1)

            # Step 3: 计算注意力分数
            # attention_scores: [batch, 3]
            attention_scores = self.ent_attn(x_stack).squeeze(-1)

            # Step 4: Softmax归一化得到权重
            attention_weights = torch.softmax(attention_scores, dim=-1)  # [batch, 3]

            # Step 5: 加权求和
            # attention_weights.unsqueeze(-1): [batch, 3, 1]
            # context_vectors: [batch, out_dim]
            context_vectors = torch.sum(
                attention_weights.unsqueeze(-1) * x_stack, dim=1
            )

            x_mm.append(context_vectors)

        # Step 6: 叠加所有路径的结果
        # x_mm: [batch, multi, out_dim]
        x_mm = torch.stack(x_mm, dim=1)

        # 求和得到最终融合结果
        fused = x_mm.sum(1).view(batch_size, self.out_dim)  # [batch, out_dim]

        # 返回融合结果和注意力权重（最后一次迭代的权重）
        return fused, attention_weights
