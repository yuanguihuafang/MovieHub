"""
模型辅助模块 - 对比学习和互信息估计

包含：
    - Similarity: 相似度计算（点积或余弦相似度）
    - ContrastiveLoss: 对比损失（用于对比学习）
    - CLUBSample: 互信息估计器（CLUB算法）
    - MIEstimator: 多模态互信息估计器

用途：
    - 用于解耦不同模态的表示
    - 促进不同专家学习互补的知识
"""

import torch
import torch.nn as nn
import random

# 相似度计算
class Similarity(nn.Module):
    """
    相似度计算模块

    支持：
        点积相似度
        带温度系数的余弦相似度
    """
    def __init__(self, temp):
        super().__init__()
        self.temp = temp # 温度系数
        self.cos = nn.CosineSimilarity(dim=-1)

    def forward(self, x, y):

        return self.cos(x, y) / self.temp

# 对比损失
class ContrastiveLoss(nn.Module):
    """
    对比损失 - 用于对比学习

    原理：
        - 将同一样本的不同视图拉近
        - 将不同样本的视图推远
        - 使用InfoNCE损失实现
    """

    def __init__(self, temp=0.5):
        super().__init__()
        self.loss = nn.CrossEntropyLoss()
        self.sim_func = Similarity(temp=temp)

    def forward(self, emb1, emb2):
        # 计算批次内所有对的相似度矩阵
        # [batch, 1, dim] vs [1, batch, dim] -> [batch, batch]
        batch_sim = self.sim_func(emb1.unsqueeze(1), emb2.unsqueeze(0))

        # 对角线位置为正样本（自身对比）
        labels = torch.arange(batch_sim.size(0)).long().to("cuda")

        return self.loss(batch_sim, labels)

# 互信息估计器 (CLUB)
class CLUBSample(nn.Module):
    """
    CLUB (Contrastive Log-Upper Bound) 互信息估计器

    原理：
        - 使用变分上界估计互信息
        - 通过X预测Y的均值和方差来估计

    用途：
        - 估计两个随机变量之间的互信息
        - 用于解耦学习，促进不同模态表示的独立性

    参考：CLUB: A Contrastive Log-Upper Bound of Mutual Information
    """

    def __init__(self, x_dim, y_dim, hidden_size):
        super(CLUBSample, self).__init__()

        # 预测Y的均值网络：X -> mu
        self.p_mu = nn.Sequential(
            nn.Linear(x_dim, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, y_dim),
        )

        # 预测Y的对数方差网络：X -> log(var)
        self.p_logvar = nn.Sequential(
            nn.Linear(x_dim, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, y_dim),
            nn.Tanh(),  # 限制在[-1, 1]
        )
    # 获取均值和对数方差
    def get_mu_logvar(self, x_samples):
        mu = self.p_mu(x_samples)
        logvar = self.p_logvar(x_samples)
        return mu, logvar

    def forward(self, x_samples, y_samples):
        sample_size = x_samples.shape[0]

        # 随机打乱Y的顺序，构造负样本
        random_index = torch.randperm(sample_size).long()

        # 获取X预测Y的均值和方差
        mu, logvar = self.get_mu_logvar(x_samples)

        # 正样本对：相似度
        positive = -((mu - x_samples[random_index]) ** 2) / logvar.exp()

        # 负样本对：相似度
        negative = -((mu - y_samples[random_index]) ** 2) / logvar.exp()

        # 互信息上界（用于训练判别器）
        upper_bound = (positive.sum(dim=-1) - negative.sum(dim=-1)).mean()

        return upper_bound / 2.0

    # 计算对数似然（更新用）
    def loglikeli(self, x_samples, y_samples):
        mu, logvar = self.get_mu_logvar(x_samples)
        return (-((mu - y_samples) ** 2) / 2.0 / logvar.exp()).sum(dim=1).mean(dim=0)

    # 学习损失（负对数似然）
    def learning_loss(self, x_samples, y_samples):
        return -self.loglikeli(x_samples, y_samples)

# 多模态互信息估计器
class MIEstimator(nn.Module):
    """
    多模态互信息估计器

    作用：
        - 分别估计结构、图像、文本三种模态表示之间的互信息
        - 通过对比不同专家的表示，促进模态间的解耦

    使用方式：
        - 在训练时，随机选择两个专家的表示进行对比
        - 计算三者（结构、图像、文本）的平均互信息损失
    """

    def __init__(self, args):
        """
        初始化多模态互信息估计器

        参数：
            args: 
                - dim: 结构嵌入维度
                - img_dim: 图像嵌入维度
                - txt_dim: 文本嵌入维度
                - n_exp: 专家数量
        """
        super(MIEstimator, self).__init__()

        # 为每种模态创建独立的CLUB估计器
        self.str_estimator = CLUBSample(args.dim, args.dim, args.dim)
        self.img_estimator = CLUBSample(args.img_dim, args.img_dim, args.img_dim)
        self.txt_estimator = CLUBSample(args.txt_dim, args.txt_dim, args.txt_dim)

        # 专家数量
        self.num = args.n_exp

    def forward(self, embeddings):
        strs, imgs, txts = embeddings

        # 随机选择两个专家进行对比
        idx1, idx2 = random.sample(range(self.num), k=2)
        str1, str2 = strs[idx1], strs[idx2]
        img1, img2 = imgs[idx1], imgs[idx2]
        txt1, txt2 = txts[idx1], txts[idx2]

        # 计算三个模态的平均互信息损失
        mi_loss = (
            self.str_estimator(str1, str2)
            + self.img_estimator(img1, img2)
            + self.txt_estimator(txt1, txt2)
        ) / 3.0

        return mi_loss
    
    # 训练估计器：计算学习损失（更新估计器参数）
    def train_estimator(self, embeddings):
        strs, imgs, txts = embeddings

        # 随机选择两个专家
        idx1, idx2 = random.sample(range(self.num), k=2)
        str1, str2 = strs[idx1], strs[idx2]
        img1, img2 = imgs[idx1], imgs[idx2]
        txt1, txt2 = txts[idx1], txts[idx2]

        # 计算三个估计器的学习损失
        est_loss = (
            self.str_estimator.learning_loss(str1, str2)
            + self.img_estimator.learning_loss(img1, img2)
            + self.txt_estimator.learning_loss(txt1, txt2)
        ) / 3.0

        return est_loss
