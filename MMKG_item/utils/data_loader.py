"""
数据加载器模块 - 知识图谱训练和评估的数据处理

包含：
    - Corpus: 数据集基类
    - ConvECorpus: 本项目使用的数据加载器（核心类）
    - ConvKBCorpus: ConvKB使用的数据加载器

功能：
    - 管理训练/验证/测试数据集
    - 提供批次数据迭代
    - 支持负采样（ConvKB）
    - 构建(头,关系)->尾实体的映射
    - 添加逆关系支持双向预测
    - 计算评估指标（MRR, Hits@K, MR）

核心概念：
    1. 双向训练：为每个关系r创建逆关系-r，训练时同时学习预测头尾
    2. 多标签：一个(头,关系)可能对应多个尾实体
    3. 评估时过滤已知三元组，确保评估公平性
"""
import torch
import numpy as np
from collections import defaultdict

class Corpus:
    """
    数据集基类 - 定义数据加载器的通用接口
    """
    def __init__(self, args, train_data, val_data, test_data, entity2id, relation2id):
        self.device = args.device
        self.train_triples = train_data[0]
        self.val_triples = val_data[0]
        self.test_triples = test_data[0]
        self.max_batch_num = 1

        # 构建邻接矩阵（用于图神经网络等）
        adj_indices = torch.LongTensor([train_data[1][0], train_data[1][1]])
        adj_values = torch.LongTensor([train_data[1][2]])
        self.train_adj_matrix = (adj_indices, adj_values)

        self.entity2id = {k: v for k, v in entity2id.items()}
        self.id2entity = {v: k for k, v in entity2id.items()}
        self.relation2id = {k: v for k, v in relation2id.items()}
        self.id2relation = {v: k for k, v in relation2id.items()}
        self.batch_size = args.batch_size

    def shuffle(self):
        raise NotImplementedError

    def get_batch(self, batch_num):
        raise NotImplementedError

    def get_validation_pred(self, model, split="test"):
        raise NotImplementedError


class ConvECorpus(Corpus):
    """
    本项目使用的主要数据加载器

    特点：
        - 自动添加逆关系（每个关系r创建-r）
        - 双向训练：同时预测尾实体和头实体
        - 支持多标签：同一(头,关系)可能有多个尾实体
    """

    def __init__(self, args, train_data, val_data, test_data, entity2id, relation2id):
        super(ConvECorpus, self).__init__(
            args, train_data, val_data, test_data, entity2id, relation2id
        )
        rel_num = len(relation2id)

        # 添加逆关系
        for k, v in relation2id.items():
            self.relation2id[k + "_reverse"] = v + rel_num
        self.id2relation = {v: k for k, v in self.relation2id.items()}

        # 构建(头,关系)->尾实体映射
        sr2o = {}  # subject+relation->object(sr2o)
        for head, relation, tail in self.train_triples:
            if (head, relation) not in sr2o.keys():
                sr2o[(head, relation)] = set()
            if (tail, relation + rel_num) not in sr2o.keys():
                sr2o[(tail, relation + rel_num)] = set()
            sr2o[(head, relation)].add(tail)
            sr2o[(tail, relation + rel_num)].add(head)

        # 构建训练集索引，方便后续批量训练
        self.triples = {}
        self.train_indices = [
            {"triple": (a, b, -1), "label": list(sr2o[(a, b)])}
            for (a, b), c in sr2o.items()
        ]
        self.triples["train"] = [
            {"triple": (head, relation, -1), "label": list(sr2o[(head, relation)])}
            for (head, relation), tail in sr2o.items()
        ]

        # 计算批次数
        if len(self.train_indices) % self.batch_size == 0:
            self.max_batch_num = len(self.train_indices) // self.batch_size
        else:
            self.max_batch_num = len(self.train_indices) // self.batch_size + 1

        # 构建验证/测试集索引（加入sr2o确保覆盖）
        # 与训练集不同的是，验证集和测试集的三元组，都是直接进行尾实体的预测
        # 而训练集是先进行尾实体的预测，然后再进行头实体的预测
        for head, relation, tail in self.val_triples:
            if (head, relation) not in sr2o.keys():
                sr2o[(head, relation)] = set()
            if (tail, relation + rel_num) not in sr2o.keys():
                sr2o[(tail, relation + rel_num)] = set()
            sr2o[(head, relation)].add(tail)
            sr2o[(tail, relation + rel_num)].add(head)

        for head, relation, tail in self.test_triples:
            if (head, relation) not in sr2o.keys():
                sr2o[(head, relation)] = set()
            if (tail, relation + rel_num) not in sr2o.keys():
                sr2o[(tail, relation + rel_num)] = set()
            sr2o[(head, relation)].add(tail)
            sr2o[(tail, relation + rel_num)].add(head)

        # 验证/测试集头尾预测索引
        self.val_head_indices = [
            {
                "triple": (tail, relation + rel_num, head),
                "label": list(sr2o[(tail, relation + rel_num)]),
            }
            for (head, relation, tail) in self.val_triples
        ]
        self.val_tail_indices = [
            {"triple": (head, relation, tail), "label": list(sr2o[(head, relation)])}
            for (head, relation, tail) in self.val_triples
        ]
        self.test_head_indices = [
            {
                "triple": (tail, relation + rel_num, head),
                "label": list(sr2o[(tail, relation + rel_num)]),
            }
            for (head, relation, tail) in self.test_triples
        ]
        self.test_tail_indices = [
            {"triple": (head, relation, tail), "label": list(sr2o[(head, relation)])}
            for (head, relation, tail) in self.test_triples
        ]

        self.hits1 = 0
        self.hits3 = 0
        self.hits10 = 0
        self.hits100 = 0
        self.mean_rank = 0

    def read_batch(self, batch):
        triple, label = [_.to(self.device) for _ in batch]
        return triple, label

    def shuffle(self):
        np.random.shuffle(self.train_indices)

    # 训练阶段，每次获取一个batch的训练数据，获取训练集输入，构造训练集标签
    def get_batch(self, batch_num):
        """获取训练批次"""
        if (batch_num + 1) * self.batch_size <= len(self.train_indices):
            batch = self.train_indices[
                batch_num * self.batch_size : (batch_num + 1) * self.batch_size
            ]
        else:
            batch = self.train_indices[batch_num * self.batch_size :]

        batch_indices = torch.LongTensor([indice["triple"] for indice in batch])
        label = [np.int32(indice["label"]) for indice in batch]

        # 构建标签矩阵
        y = np.zeros((len(batch), len(self.entity2id)), dtype=np.float32)
        for idx in range(len(label)):
            for l in label[idx]:
                y[idx][l] = 1.0
        y = 0.9 * y + (1.0 / len(self.entity2id))
        batch_values = torch.FloatTensor(y)

        return batch_indices, batch_values

    def get_validation_pred(self, model, split="test"):
        """评估模型性能"""
        ranks_head, ranks_tail = [], []
        reciprocal_ranks_head, reciprocal_ranks_tail = [], []
        hits_at_100_head, hits_at_100_tail = 0, 0
        hits_at_10_head, hits_at_10_tail = 0, 0
        hits_at_3_head, hits_at_3_tail = 0, 0
        hits_at_1_head, hits_at_1_tail = 0, 0

        rel_pred_dict = defaultdict(list)
        att_s, att_i, att_t, att_mm = [], [], [], []

        if split == "val":
            head_indices = self.val_head_indices
            tail_indices = self.val_tail_indices
        else:
            head_indices = self.test_head_indices
            tail_indices = self.test_tail_indices

        if len(head_indices) % self.batch_size == 0:
            max_batch_num = len(head_indices) // self.batch_size
        else:
            max_batch_num = len(head_indices) // self.batch_size + 1

        # 遍历所有batch，获取每个batch的验证数据，进行验证预测
        for batch_num in range(max_batch_num):
            # 获取本批次数据
            if (batch_num + 1) * self.batch_size <= len(head_indices):
                head_batch = head_indices[
                    batch_num * self.batch_size : (batch_num + 1) * self.batch_size
                ]
                tail_batch = tail_indices[
                    batch_num * self.batch_size : (batch_num + 1) * self.batch_size
                ]
            else:
                head_batch = head_indices[batch_num * self.batch_size :]
                tail_batch = tail_indices[batch_num * self.batch_size :]

            # ========== 头实体预测 ==========
            head_batch_indices = torch.LongTensor(
                [indice["triple"] for indice in head_batch]
            )
            head_batch_indices = head_batch_indices.to(self.device)
            rel_ids = head_batch_indices[:, 1]

            pred, attention = model.forward(head_batch_indices, self.train_adj_matrix)

            # 保存注意力权重
            for i in range(pred[0].shape[0]):
                h, r, t = (
                    head_batch_indices[i][0].item(),
                    head_batch_indices[i][1].item(),
                    head_batch_indices[i][2].item(),
                )
                att_s.append((h, r, t, attention[0][i]))
                att_i.append((h, r, t, attention[1][i]))
                att_t.append((h, r, t, attention[2][i]))
                att_mm.append((h, r, t, attention[3][i]))

            # 四分支预测取平均
            pred = (pred[0] + pred[1] + pred[2] + pred[3]) / 4.0

            # 构建标签矩阵
            label = [np.int32(indice["label"]) for indice in head_batch]
            y = np.zeros((len(head_batch), len(self.entity2id)), dtype=np.float32)
            for idx in range(len(label)):
                for l in label[idx]:
                    y[idx][l] = 1.0
            y = torch.FloatTensor(y).to(self.device)

            # 计算排名
            target = head_batch_indices[:, 2]
            b_range = torch.arange(pred.shape[0], device=self.device)
            target_pred = pred[b_range, target]
            pred = torch.where(y.byte(), torch.zeros_like(pred), pred)
            pred[b_range, target] = target_pred
            pred = pred.cpu().numpy()
            target = target.cpu().numpy()

            for i in range(pred.shape[0]):
                scores = pred[i]
                tar = target[i]
                tar_scr = scores[tar]
                scores = np.delete(scores, tar)
                rand = np.random.randint(scores.shape[0])
                scores = np.insert(scores, rand, tar_scr)
                sorted_indices = np.argsort(-scores, kind="stable")
                ranks_head.append(np.where(sorted_indices == rand)[0][0] + 1)
                reciprocal_ranks_head.append(1.0 / ranks_head[-1])
                rel_pred_dict[rel_ids[i].item()].append(ranks_head[-1])

            # ========== 尾实体预测 ==========
            tail_batch_indices = torch.LongTensor(
                [indice["triple"] for indice in tail_batch]
            )
            tail_batch_indices = tail_batch_indices.to(self.device)
            rel_ids = tail_batch_indices[:, 1]

            pred, attention = model.forward(tail_batch_indices, self.train_adj_matrix)

            for i in range(pred[0].shape[0]):
                h, r, t = (
                    tail_batch_indices[i][0].item(),
                    tail_batch_indices[i][1].item(),
                    tail_batch_indices[i][2].item(),
                )
                att_s.append((h, r, t, attention[0][i]))
                att_i.append((h, r, t, attention[1][i]))
                att_t.append((h, r, t, attention[2][i]))
                att_mm.append((h, r, t, attention[3][i]))

            pred = (pred[0] + pred[1] + pred[2] + pred[3]) / 4.0

            label = [np.int32(indice["label"]) for indice in tail_batch]
            y = np.zeros((len(tail_batch), len(self.entity2id)), dtype=np.float32)
            for idx in range(len(label)):
                for l in label[idx]:
                    y[idx][l] = 1.0
            y = torch.FloatTensor(y).to(self.device)

            target = tail_batch_indices[:, 2]
            b_range = torch.arange(pred.shape[0], device=self.device)
            target_pred = pred[b_range, target]
            pred = torch.where(y.byte(), torch.zeros_like(pred), pred)
            pred[b_range, target] = target_pred
            pred = pred.cpu().numpy()
            target = target.cpu().numpy()

            for i in range(pred.shape[0]):
                scores = pred[i]
                tar = target[i]
                tar_scr = scores[tar]
                scores = np.delete(scores, tar)
                rand = np.random.randint(scores.shape[0])
                scores = np.insert(scores, rand, tar_scr)
                sorted_indices = np.argsort(-scores, kind="stable")
                ranks_tail.append(np.where(sorted_indices == rand)[0][0] + 1)
                reciprocal_ranks_tail.append(1.0 / ranks_tail[-1])
                rel_pred_dict[rel_ids[i].item()].append(ranks_head[-1])

        # 统计指标
        for i in range(len(ranks_head)):
            if ranks_head[i] <= 100:
                hits_at_100_head += 1
            if ranks_head[i] <= 10:
                hits_at_10_head += 1
            if ranks_head[i] <= 3:
                hits_at_3_head += 1
            if ranks_head[i] == 1:
                hits_at_1_head += 1

        for i in range(len(ranks_tail)):
            if ranks_tail[i] <= 100:
                hits_at_100_tail += 1
            if ranks_tail[i] <= 10:
                hits_at_10_tail += 1
            if ranks_tail[i] <= 3:
                hits_at_3_tail += 1
            if ranks_tail[i] == 1:
                hits_at_1_tail += 1
        # 计算头实体指标
        hits_100_head = hits_at_100_head / len(ranks_head)
        hits_10_head = hits_at_10_head / len(ranks_head)
        hits_3_head = hits_at_3_head / len(ranks_head)
        hits_1_head = hits_at_1_head / len(ranks_head)
        mean_rank_head = sum(ranks_head) / len(ranks_head)
        mean_reciprocal_rank_head = sum(reciprocal_ranks_head) / len(
            reciprocal_ranks_head
        )
        # 计算尾实体指标
        hits_100_tail = hits_at_100_tail / len(ranks_tail)
        hits_10_tail = hits_at_10_tail / len(ranks_tail)
        hits_3_tail = hits_at_3_tail / len(ranks_tail)
        hits_1_tail = hits_at_1_tail / len(ranks_tail)
        mean_rank_tail = sum(ranks_tail) / len(ranks_tail)
        mean_reciprocal_rank_tail = sum(reciprocal_ranks_tail) / len(
            reciprocal_ranks_tail
        )

        # 综合指标
        hits_100 = (hits_100_head + hits_100_tail) / 2
        hits_10 = (hits_10_head + hits_10_tail) / 2
        hits_3 = (hits_3_head + hits_3_tail) / 2
        hits_1 = (hits_1_head + hits_1_tail) / 2
        mean_rank = (mean_rank_head + mean_rank_tail) / 2
        mean_reciprocal_rank = (
            mean_reciprocal_rank_head + mean_reciprocal_rank_tail
        ) / 2

        metrics = {
            "Hits@100": hits_100,
            "Hits@10": hits_10,
            "Hits@3": hits_3,
            "Hits@1": hits_1,
            "MR": mean_rank,
            "MRR": mean_reciprocal_rank,
        }

        return metrics, [att_s, att_i, att_t, att_mm]

    def get_validation_pred_signle(self, model, split="test", index=0):
        """单分支评估"""
        ranks_head, ranks_tail = [], []
        reciprocal_ranks_head, reciprocal_ranks_tail = [], []
        hits_at_100_head, hits_at_100_tail = 0, 0
        hits_at_10_head, hits_at_10_tail = 0, 0
        hits_at_3_head, hits_at_3_tail = 0, 0
        hits_at_1_head, hits_at_1_tail = 0, 0
        rel_pred_dict = defaultdict(list)

        if split == "val":
            head_indices = self.val_head_indices
            tail_indices = self.val_tail_indices
        else:
            head_indices = self.test_head_indices
            tail_indices = self.test_tail_indices

        if len(head_indices) % self.batch_size == 0:
            max_batch_num = len(head_indices) // self.batch_size
        else:
            max_batch_num = len(head_indices) // self.batch_size + 1
        for batch_num in range(max_batch_num):
            if (batch_num + 1) * self.batch_size <= len(head_indices):
                head_batch = head_indices[
                    batch_num * self.batch_size : (batch_num + 1) * self.batch_size
                ]
                tail_batch = tail_indices[
                    batch_num * self.batch_size : (batch_num + 1) * self.batch_size
                ]
            else:
                head_batch = head_indices[batch_num * self.batch_size :]
                tail_batch = tail_indices[batch_num * self.batch_size :]

            head_batch_indices = torch.LongTensor(
                [indice["triple"] for indice in head_batch]
            )
            head_batch_indices = head_batch_indices.to(self.device)
            rel_ids = head_batch_indices[:, 1]
            pred, _ = model.forward(head_batch_indices, self.train_adj_matrix)
            pred = pred[index]
            label = [np.int32(indice["label"]) for indice in head_batch]
            y = np.zeros((len(head_batch), len(self.entity2id)), dtype=np.float32)
            for idx in range(len(label)):
                for l in label[idx]:
                    y[idx][l] = 1.0
            y = torch.FloatTensor(y).to(self.device)
            target = head_batch_indices[:, 2]
            b_range = torch.arange(pred.shape[0], device=self.device)
            target_pred = pred[b_range, target]
            pred = torch.where(y.byte(), torch.zeros_like(pred), pred)
            pred[b_range, target] = target_pred
            pred = pred.cpu().numpy()
            target = target.cpu().numpy()
            for i in range(pred.shape[0]):
                scores = pred[i]
                tar = target[i]
                tar_scr = scores[tar]
                scores = np.delete(scores, tar)
                rand = np.random.randint(scores.shape[0])
                scores = np.insert(scores, rand, tar_scr)
                sorted_indices = np.argsort(-scores, kind="stable")
                ranks_head.append(np.where(sorted_indices == rand)[0][0] + 1)
                reciprocal_ranks_head.append(1.0 / ranks_head[-1])
                rel_pred_dict[rel_ids[i].item()].append(ranks_head[-1])

            tail_batch_indices = torch.LongTensor(
                [indice["triple"] for indice in tail_batch]
            )
            tail_batch_indices = tail_batch_indices.to(self.device)
            rel_ids = tail_batch_indices[:, 1]
            pred = model.forward(tail_batch_indices, self.train_adj_matrix)[0][index]
            label = [np.int32(indice["label"]) for indice in tail_batch]
            y = np.zeros((len(tail_batch), len(self.entity2id)), dtype=np.float32)
            for idx in range(len(label)):
                for l in label[idx]:
                    y[idx][l] = 1.0
            y = torch.FloatTensor(y).to(self.device)
            target = tail_batch_indices[:, 2]
            b_range = torch.arange(pred.shape[0], device=self.device)
            target_pred = pred[b_range, target]
            pred = torch.where(y.byte(), torch.zeros_like(pred), pred)
            pred[b_range, target] = target_pred
            pred = pred.cpu().numpy()
            target = target.cpu().numpy()
            for i in range(pred.shape[0]):
                scores = pred[i]
                tar = target[i]
                tar_scr = scores[tar]
                scores = np.delete(scores, tar)
                rand = np.random.randint(scores.shape[0])
                scores = np.insert(scores, rand, tar_scr)
                sorted_indices = np.argsort(-scores, kind="stable")
                ranks_tail.append(np.where(sorted_indices == rand)[0][0] + 1)
                reciprocal_ranks_tail.append(1.0 / ranks_tail[-1])
                rel_pred_dict[rel_ids[i].item()].append(ranks_head[-1])

        for i in range(len(ranks_head)):
            if ranks_head[i] <= 100:
                hits_at_100_head += 1
            if ranks_head[i] <= 10:
                hits_at_10_head += 1
            if ranks_head[i] <= 3:
                hits_at_3_head += 1
            if ranks_head[i] == 1:
                hits_at_1_head += 1

        for i in range(len(ranks_tail)):
            if ranks_tail[i] <= 100:
                hits_at_100_tail += 1
            if ranks_tail[i] <= 10:
                hits_at_10_tail += 1
            if ranks_tail[i] <= 3:
                hits_at_3_tail += 1
            if ranks_tail[i] == 1:
                hits_at_1_tail += 1

        hits_100_head = hits_at_100_head / len(ranks_head)
        hits_10_head = hits_at_10_head / len(ranks_head)
        hits_3_head = hits_at_3_head / len(ranks_head)
        hits_1_head = hits_at_1_head / len(ranks_head)
        mean_rank_head = sum(ranks_head) / len(ranks_head)
        mean_reciprocal_rank_head = sum(reciprocal_ranks_head) / len(
            reciprocal_ranks_head
        )

        hits_100_tail = hits_at_100_tail / len(ranks_tail)
        hits_10_tail = hits_at_10_tail / len(ranks_tail)
        hits_3_tail = hits_at_3_tail / len(ranks_tail)
        hits_1_tail = hits_at_1_tail / len(ranks_tail)
        mean_rank_tail = sum(ranks_tail) / len(ranks_tail)
        mean_reciprocal_rank_tail = sum(reciprocal_ranks_tail) / len(
            reciprocal_ranks_tail
        )

        hits_100 = (hits_100_head + hits_100_tail) / 2
        hits_10 = (hits_10_head + hits_10_tail) / 2
        hits_3 = (hits_3_head + hits_3_tail) / 2
        hits_1 = (hits_1_head + hits_1_tail) / 2
        mean_rank = (
            sum(ranks_head) / len(ranks_head) + sum(ranks_tail) / len(ranks_tail)
        ) / 2
        mean_reciprocal_rank = (
            sum(reciprocal_ranks_head) / len(reciprocal_ranks_head)
            + sum(reciprocal_ranks_tail) / len(reciprocal_ranks_tail)
        ) / 2

        metrics = {
            "Hits@100": hits_100,
            "Hits@10": hits_10,
            "Hits@3": hits_3,
            "Hits@1": hits_1,
            "MR": mean_rank,
            "MRR": mean_reciprocal_rank,
        }

        return metrics, rel_pred_dict


class ConvKBCorpus(Corpus):
    """ConvKB数据集类 - 使用负采样进行训练"""

    def __init__(self, args, train_data, val_data, test_data, entity2id, relation2id):
        super(ConvKBCorpus, self).__init__(
            args, train_data, val_data, test_data, entity2id, relation2id
        )
        self.neg_num = args.neg_num
        if len(self.train_triples) % self.batch_size == 0:
            self.max_batch_num = len(self.train_triples) // self.batch_size
        else:
            self.max_batch_num = len(self.train_triples) // self.batch_size + 1

        self.train_indices = np.array(self.train_triples).astype(np.int32)
        self.train_values = np.array([[1]] * len(self.train_triples)).astype(np.float32)
        self.val_indices = np.array(self.val_triples).astype(np.int32)
        self.val_values = np.array([[1]] * len(self.val_triples)).astype(np.float32)
        self.test_indices = np.array(self.test_triples).astype(np.int32)
        self.test_values = np.array([[1]] * len(self.test_triples)).astype(np.float32)

        self.unique_entities = [entity2id[i] for i in train_data[2]]
        self.all_triples = {
            j: i
            for i, j in enumerate(
                self.train_triples + self.val_triples + self.test_triples
            )
        }

        self.batch_indices = np.empty((self.batch_size * (self.neg_num + 1), 3)).astype(
            np.int32
        )
        self.batch_values = np.empty((self.batch_size * (self.neg_num + 1), 1)).astype(
            np.float32
        )

    def shuffle(self):
        np.random.shuffle(self.train_indices)

    def get_batch(self, batch_num):
        """获取批次（包含负样本）"""
        if (batch_num + 1) * self.batch_size <= len(self.train_indices):
            self.batch_indices = np.empty(
                (self.batch_size * (self.neg_num + 1), 3)
            ).astype(np.int32)
            self.batch_values = np.empty(
                (self.batch_size * (self.neg_num + 1), 1)
            ).astype(np.float32)
            indices = range(
                self.batch_size * batch_num, self.batch_size * (batch_num + 1)
            )
            last_index = self.batch_size
        else:
            last_batch_size = len(self.train_indices) - self.batch_size * batch_num
            self.batch_indices = np.empty(
                (last_batch_size * (self.neg_num + 1), 3)
            ).astype(np.int32)
            self.batch_values = np.empty(
                (last_batch_size * (self.neg_num + 1), 1)
            ).astype(np.float32)
            indices = range(self.batch_size * batch_num, len(self.train_indices))
            last_index = last_batch_size

        self.batch_indices[:last_index, :] = self.train_indices[indices, :]
        self.batch_values[:last_index, :] = self.train_values[indices, :]
        random_entities = np.random.randint(
            0, len(self.entity2id), last_index * self.neg_num
        )
        self.batch_indices[last_index : (last_index * (self.neg_num + 1)), :] = np.tile(
            self.batch_indices[:last_index, :], (self.neg_num, 1)
        )
        self.batch_values[last_index : (last_index * (self.neg_num + 1)), :] = np.tile(
            self.batch_values[:last_index, :], (self.neg_num, 1)
        )

        for i in range(last_index):
            for j in range(self.neg_num // 2):
                current_index = i * (self.neg_num // 2) + j
                while (
                    random_entities[current_index],
                    self.batch_indices[last_index + current_index, 1],
                    self.batch_indices[last_index + current_index, 2],
                ) in self.all_triples.keys():
                    random_entities[current_index] = np.random.randint(
                        0, len(self.entity2id)
                    )
                self.batch_indices[last_index + current_index, 0] = random_entities[
                    current_index
                ]
                self.batch_values[last_index + current_index, :] = [-1]
            for j in range(self.neg_num // 2):
                current_index = (
                    last_index * (self.neg_num // 2) + i * (self.neg_num // 2) + j
                )
                while (
                    self.batch_indices[last_index + current_index, 0],
                    self.batch_indices[last_index + current_index, 1],
                    random_entities[current_index],
                ) in self.all_triples.keys():
                    random_entities[current_index] = np.random.randint(
                        0, len(self.entity2id)
                    )
                self.batch_indices[last_index + current_index, 2] = random_entities[
                    current_index
                ]
                self.batch_values[last_index + current_index, :] = [-1]

        return self.batch_indices, self.batch_values

    def get_validation_pred(self, model, split="test"):
        """评估"""
        ranks_head, ranks_tail = [], []
        reciprocal_ranks_head, reciprocal_ranks_tail = [], []
        hits_at_100_head, hits_at_100_tail = 0, 0
        hits_at_10_head, hits_at_10_tail = 0, 0
        hits_at_3_head, hits_at_3_tail = 0, 0
        hits_at_1_head, hits_at_1_tail = 0, 0
        entity_list = [i for i in self.entity2id.values()]
        if split == "val":
            split_triples = np.array(self.val_triples).astype(np.int32)
        elif split == "test":
            split_triples = np.array(self.test_triples).astype(np.int32)

        for i in range(split_triples.shape[0]):
            if (
                split_triples[i, 0] not in self.unique_entities
                or split_triples[i, 2] not in self.unique_entities
            ):
                continue
            x_head = np.tile(split_triples[i, :], (len(self.entity2id), 1))
            x_tail = np.tile(split_triples[i, :], (len(self.entity2id), 1))
            x_head[:, 0] = entity_list
            x_tail[:, 2] = entity_list

            last_index_head, last_index_tail = [], []
            for idx in range(len(x_head)):
                head = (x_head[idx][0], x_head[idx][1], x_head[idx][2])
                if head in self.all_triples.keys():
                    last_index_head.append(idx)
                tail = (x_tail[idx][0], x_tail[idx][1], x_tail[idx][2])
                if tail in self.all_triples.keys():
                    last_index_tail.append(idx)

            x_head = np.delete(x_head, last_index_head, axis=0)
            x_tail = np.delete(x_tail, last_index_tail, axis=0)
            rand_head = np.random.randint(x_head.shape[0])
            rand_tail = np.random.randint(x_tail.shape[0])
            x_head = np.insert(x_head, rand_head, split_triples[i], axis=0)
            x_tail = np.insert(x_tail, rand_tail, split_triples[i], axis=0)
            x_head = torch.LongTensor(x_head).to(self.device)
            x_tail = torch.LongTensor(x_tail).to(self.device)
            scores_head = model.predict(x_head)
            sorted_scores_head, sorted_triples_head = torch.sort(
                scores_head.view(-1), dim=-1, descending=True
            )
            ranks_head.append(
                np.where(sorted_triples_head.cpu().numpy() == rand_head)[0][0] + 1
            )
            reciprocal_ranks_head.append(1.0 / ranks_head[-1])
            scores_tail = model.predict(x_tail)
            sorted_scores_tail, sorted_triples_tail = torch.sort(
                scores_tail.view(-1), dim=-1, descending=True
            )
            ranks_tail.append(
                np.where(sorted_triples_tail.cpu().numpy() == rand_tail)[0][0] + 1
            )
            reciprocal_ranks_tail.append(1.0 / ranks_tail[-1])

        for i in range(len(ranks_head)):
            if ranks_head[i] <= 100:
                hits_at_100_head += 1
            if ranks_head[i] <= 10:
                hits_at_10_head += 1
            if ranks_head[i] <= 3:
                hits_at_3_head += 1
            if ranks_head[i] == 1:
                hits_at_1_head += 1

        for i in range(len(ranks_tail)):
            if ranks_tail[i] <= 100:
                hits_at_100_tail += 1
            if ranks_tail[i] <= 10:
                hits_at_10_tail += 1
            if ranks_tail[i] <= 3:
                hits_at_3_tail += 1
            if ranks_tail[i] == 1:
                hits_at_1_tail += 1

        hits_100_head = hits_at_100_head / len(ranks_head)
        hits_10_head = hits_at_10_head / len(ranks_head)
        hits_3_head = hits_at_3_head / len(ranks_head)
        hits_1_head = hits_at_1_head / len(ranks_head)
        mean_rank_head = sum(ranks_head) / len(ranks_head)
        mean_reciprocal_rank_head = sum(reciprocal_ranks_head) / len(
            reciprocal_ranks_head
        )

        hits_100_tail = hits_at_100_tail / len(ranks_tail)
        hits_10_tail = hits_at_10_tail / len(ranks_tail)
        hits_3_tail = hits_at_3_tail / len(ranks_tail)
        hits_1_tail = hits_at_1_tail / len(ranks_tail)
        mean_rank_tail = sum(ranks_tail) / len(ranks_tail)
        mean_reciprocal_rank_tail = sum(reciprocal_ranks_tail) / len(
            reciprocal_ranks_tail
        )

        hits_100 = (hits_100_head + hits_100_tail) / 2
        hits_10 = (hits_10_head + hits_10_tail) / 2
        hits_3 = (hits_3_head + hits_3_tail) / 2
        hits_1 = (hits_1_head + hits_1_tail) / 2
        mean_rank = (
            sum(ranks_head) / len(ranks_head) + sum(ranks_tail) / len(ranks_tail)
        ) / 2
        mean_reciprocal_rank = (
            sum(reciprocal_ranks_head) / len(reciprocal_ranks_head)
            + sum(reciprocal_ranks_tail) / len(reciprocal_ranks_tail)
        ) / 2

        metrics = {
            "Hits@100_head": hits_100_head,
            "Hits@10_head": hits_10_head,
            "Hits@3_head": hits_3_head,
            "Hits@1_head": hits_1_head,
            "Mean Rank_head": mean_rank_head,
            "Mean Reciprocal Rank_head": mean_reciprocal_rank_head,
            "Hits@100_tail": hits_100_tail,
            "Hits@10_tail": hits_10_tail,
            "Hits@3_tail": hits_3_tail,
            "Hits@1_tail": hits_1_tail,
            "Mean Rank_tail": mean_rank_tail,
            "Mean Reciprocal Rank_tail": mean_reciprocal_rank_tail,
            "Hits@100": hits_100,
            "Hits@10": hits_10,
            "Hits@3": hits_3,
            "Hits@1": hits_1,
            "Mean Rank": mean_rank,
            "Mean Reciprocal Rank": mean_reciprocal_rank,
        }

        return metrics
