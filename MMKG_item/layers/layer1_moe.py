"""
MoE专家层模块 - Mixture of Experts 专家网络实现

包含：
    - PWLayer: 单层感知机（专家）
    - MoEAdaptorLayer: 混合专家适配层

原理：
    - MoE通过门控机制动态选择多个专家网络的输出
    - 每个专家专注于学习不同类型的特征
    - 门控网络根据输入自适应分配权重
    - 最终输出是所有专家的加权和

用途：
    - 结构MoE：处理结构嵌入
    - 视觉MoE：处理图像嵌入
    - 文本MoE：处理文本嵌入
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

# 单层感知机（专家）
class PWLayer(nn.Module):
    """
    单层感知机 - 基础的专家网络

    结构：Linear -> Dropout -> Linear

    用途：
        - 作为MoE中的专家网络
        - 对输入进行非线性变换
    """

    def __init__(self, input_size, output_size, dropout=0.0):
        """
        初始化单层感知机

        参数：
            input_size: 输入维度
            output_size: 输出维度
            dropout: Dropout概率
        """
        super(PWLayer, self).__init__()
        self.dropout = nn.Dropout(p=dropout)
        self.lin = nn.Linear(input_size, output_size)

    def forward(self, x):
        return self.lin(self.dropout(x))

# MoE适配层
class MoEAdaptorLayer(nn.Module):
    """
    混合专家适配层 - Mixture of Experts

    核心思想：
        - 维护n_exps个独立的专家网络
        - 使用门控机制计算每个专家的权重
        - 输出是所有专家的加权平均

    结构：
        - 多个PWLayer专家
        - 一个门控网络（Linear + Softmax）

    公式：
        output = Σ(g_i * expert_i(x))
        其中 g = softmax(W*x)
    """

    def __init__(self, n_exps, layers, dropout=0.0, noise=True):
        """
        初始化MoE适配层

        参数：
            n_exps: 专家数量
            layers: [input_dim, output_dim] 输入输出维度
            dropout: Dropout概率
            noise: 是否添加噪声（可选，本项目未使用）
        """
        super(MoEAdaptorLayer, self).__init__()

        self.n_exps = n_exps

        # 创建n_exps个专家网络
        # 每个专家是一个PWLayer
        self.experts = nn.ModuleList(
            [PWLayer(layers[0], layers[1], dropout) for i in range(n_exps)]
        )

        # 门控网络：将输入映射到n_exps维的权重
        # 输入维度layers[0]，输出维度n_exps
        self.gate = nn.Linear(layers[0], n_exps)

    def forward(self, x):
        """
        前向传播：计算专家加权输出

        参数：
            x: 输入张量 [batch, dim]

        返回：
            output: 加权融合后的输出 [batch, dim]
            expert_outputs: 所有专家的原始输出 [batch, n_exps, dim]
            gates: 门控权重 [batch, n_exps]
        """
        # x: [b, dim]

        # Step 1: 计算门控权重
        # gates: [batch, n_exps] - 每个专家的权重
        gates = F.softmax(self.gate(x), dim=-1)

        # Step 2: 计算每个专家的输出
        # expert_outputs: [batch, n_exps, dim]
        expert_outputs = []
        for i in range(self.n_exps):
            tmp = self.experts[i](x)  # [batch, dim]
            tmp = tmp.unsqueeze(-2)  # [batch, 1, dim]
            expert_outputs.append(tmp)

        # 拼接所有专家输出
        expert_outputs = torch.cat(expert_outputs, dim=-2)  # (B, n_exps, D)

        # Step 3: 加权求和
        # gates.unsqueeze(-1): [batch, n_exps, 1]
        # multiple_outputs: [batch, n_exps, dim]
        # sum: [batch, dim]
        multiple_outputs = gates.unsqueeze(-1) * expert_outputs
        output = multiple_outputs.sum(dim=-2)  # (b, D)

        return output, expert_outputs, gates
