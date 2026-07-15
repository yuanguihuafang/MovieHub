"""
基础模型层模块

包含：
    - LowRankerFusion: 低秩融合层
    - Swish: Swish激活函数
    - LayerNormWithResidual: 带残差的层归一化

这些是探索阶段的参考实现，当前主模型未使用。
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class LowRankerFusion(nn.Module):
    """
    低秩融合层 - 融合三模态特征（结构、图像、文本）

    原理：
        - 分别通过三个全连接层变换各模态嵌入
        - 使用元素级乘法融合三个模态
        - 再通过一个全连接层输出融合结果
    """

    def __init__(self, dim):
        super(LowRankerFusion, self).__init__()
        self.struct_fc = nn.Linear(dim, dim)
        self.txt_fc = nn.Linear(dim, dim)
        self.img_fc = nn.Linear(dim, dim)
        self.all = nn.Linear(dim, dim)

    def forward(self, s_emb, v_emb, t_emb):
        fusion_zy = 1.0
        s = self.struct_fc(s_emb)
        t = self.txt_fc(t_emb)
        v = self.img_fc(v_emb)
        fusion_zy = fusion_zy * s * t * v
        fused = self.all(fusion_zy)
        return fused


class Swish(nn.Module):
    """Swish激活函数，自门控激活函数，在深层网络中效果优于ReLU"""

    def forward(self, x):
        return x * F.sigmoid(x)


class LayerNormWithResidual(nn.Module):
    """带残差的层归一化"""

    def __init__(self, input_dim, dropout_rate=0.1):
        super(LayerNormWithResidual, self).__init__()
        self.batch_norm = nn.BatchNorm1d(input_dim * 2)
        self.linear = nn.Linear(input_dim * 2, input_dim * 2)
        self.linear2 = nn.Linear(input_dim * 2, input_dim)
        self.dropout = nn.Dropout(dropout_rate)

    def forward(self, x):
        residual = x
        x = self.linear(x)
        tmp = self.batch_norm(F.leaky_relu(x) + residual)
        return F.leaky_relu(self.linear2(tmp))

    def forward2(self, x):
        x = self.linear(x)
        residual = x
        x = self.linear2(x)
        return self.batch_norm(self.dropout(x) + residual)
