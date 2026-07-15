"""
数据处理工具模块 - 知识图谱数据的加载和预处理

功能：
    - 加载实体/关系ID映射
    - 加载三元组数据
    - 构建邻接矩阵
    - 加载多模态特征（图像、文本）
    - 数据集划分（训练/验证/测试）

数据格式说明：
    - entity2id.txt:        实体映射文件，每行 "实体URI ID"
    - relation2id.txt:      关系映射文件，每行 "关系URI ID"
    - train/valid/test.txt: 三元组文件，空格分隔 "头实体 关系 尾实体"
    - img_features.pth:     图像特征（预提取的ViT特征）
    - text_features.pth:    文本特征（预提取的BERT特征）
"""

import h5py
import pickle
import torch
import numpy as np
import os

# 获取当前模块所在目录
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# 初始项目根目录（utils的上级目录）
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
# 如果datasets不在PROJECT_ROOT下，则尝试父目录（处理嵌套结构）
if not os.path.exists(os.path.join(PROJECT_ROOT, "datasets")):
    PROJECT_ROOT = os.path.dirname(PROJECT_ROOT)


def write_index_dict(datasets):
    """
    构建实体和关系的ID映射文件

    从原始三元组文件中提取所有实体和关系，生成ID映射

    参数：
        datasets: 数据集名称

    输出：
        entity2id.txt: 实体ID映射
        relation2id.txt: 关系ID映射
    """
    path = os.path.join(PROJECT_ROOT, "datasets", datasets, "")

    entities = set()
    relations = set()

    # 遍历三元组提取实体和关系
    with open(path + datasets + "_EntityTriples.txt", "r") as f:
        for line in f:
            instance = line.strip().split(" ")
            entities.add(instance[0])  # 头实体
            relations.add(instance[1])  # 关系
            entities.add(instance[2])  # 尾实体

    # 写入实体ID映射
    with open(path + "entity2id.txt", "w") as f:
        for index, entity in enumerate(entities):
            f.write(entity + " " + str(index) + "\n")

    # 写入关系ID映射
    with open(path + "relation2id.txt", "w") as f:
        for index, relation in enumerate(relations):
            f.write(relation + " " + str(index) + "\n")


def write_img_vec(datasets):
    """
    加载图像特征并与实体ID绑定

    从HDF5文件中加载预提取的图像特征，与entity2id对齐

    参数：
        datasets: 数据集名称

    输出：
        img_features.pkl: 图像特征文件
    """
    path = os.path.join(PROJECT_ROOT, "datasets", datasets, "")

    # 读取实体到图像索引的映射
    entities = {}
    with open(path + datasets + "_ImageIndex.txt", "r") as f:
        for line in f:
            instance = line.strip().split("\t")
            entities[instance[0]] = instance[1]

    img_features = []
    with open(path + "entity2id.txt", "r") as f:
        with h5py.File(path + datasets + "_ImageData.h5", "r") as img:
            # 计算所有图像特征的均值，用于填充缺失的实体
            img_all = np.array([feats for feats in img.values()])
            img_mean = np.mean(img_all.reshape(-1, img_all.shape[2]), 0)

            # 为每个实体加载图像特征
            for line in f:
                instance = line.strip().split(" ")
                entity = instance[0]
                if entity in entities.keys():
                    img_features.append(np.array(img[entities[entity]]).flatten())
                else:
                    img_features.append(img_mean)

    img_features = np.array(img_features)
    pickle.dump(img_features, open(path + "img_features.pkl", "wb"))


def data_preprocess(datasets):
    """
    数据预处理入口函数

    依次执行：
        1. 构建ID映射
        2. 加载图像特征
        3. 划分数据集
    """
    write_index_dict(datasets)
    write_img_vec(datasets)
    dataset_split(datasets)


def read_entity_from_id(path):
    """
    读取实体ID映射文件

    参数：
        path: 数据集路径

    返回：
        entity2id: 实体名到ID的字典
    """
    if not os.path.isabs(path):
        path = os.path.join(PROJECT_ROOT, path)

    entity2id = {}
    with open(path + "entity2id.txt", "r", encoding="utf-8") as f:
        for line in f:
            instance = line.strip().split()
            entity2id[instance[0]] = int(instance[1])

    return entity2id


def read_relation_from_id(path):
    """
    读取关系ID映射文件
    """
    if not os.path.isabs(path):
        path = os.path.join(PROJECT_ROOT, path)

    relation2id = {}
    with open(path + "relation2id.txt", "r") as f:
        for line in f:
            instance = line.strip().split()
            relation2id[instance[0]] = int(instance[1])

    return relation2id


def get_adj(path, split):
    """
    加载三元组数据并构建邻接矩阵

    参数：
        path: 数据集路径
        split: 数据集划分 ('train', 'valid', 'test')

    返回：
        triples: 三元组列表 [(h_id, r_id, t_id), ...]
        adj: 邻接矩阵 (rows, cols, data)
        unique_entities: 唯一实体集合
    """
    if not os.path.isabs(path):
        path = os.path.join(PROJECT_ROOT, path)

    entity2id = read_entity_from_id(path)
    relation2id = read_relation_from_id(path)

    triples = []
    rows, cols, data = [], [], []
    unique_entities = set()

    with open(path + split + ".txt", "r", encoding="utf-8") as f:
        for line in f:
            instance = line.strip().split(" ")
            e1, r, e2 = instance[0], instance[1], instance[2]

            unique_entities.add(e1)
            unique_entities.add(e2)

            # 转换为ID
            triples.append((entity2id[e1], relation2id[r], entity2id[e2]))
            rows.append(entity2id[e2])
            cols.append(entity2id[e1])
            data.append(relation2id[r])

    return triples, (cols, rows, data), unique_entities


def load_data(datasets):
    """
    加载完整数据集

    返回：
        entity2id: 实体ID映射
        relation2id: 关系ID映射
        img_features: 图像特征张量
        text_features: 文本特征张量
        train_data: (train_triples, train_adj, train_unique_entities)
        val_data: (val_triples, val_adj, val_unique_entities)
        test_data: (test_triples, test_adj, test_unique_entities)
    """
    path = os.path.join(PROJECT_ROOT, "datasets", datasets, "")

    # 加载三元组
    train_triples, train_adj, train_unique_entities = get_adj(path, "train")
    val_triples, val_adj, val_unique_entities = get_adj(path, "valid")
    test_triples, test_adj, test_unique_entities = get_adj(path, "test")

    # 加载ID映射
    entity2id = read_entity_from_id(path)
    relation2id = read_relation_from_id(path)

    # 加载多模态特征
    img_features = torch.load(open(path + "img_features.pth", "rb"), weights_only=True)
    text_features = torch.load(
        open(path + "text_features.pth", "rb"), weights_only=True
    )

    return (
        entity2id,
        relation2id,
        img_features,
        text_features,
        (train_triples, train_adj, train_unique_entities),
        (val_triples, val_adj, val_unique_entities),
        (test_triples, test_adj, test_unique_entities),
    )


def load_more_data(datasets, numeric=True):
    """
    加载更多数据（包括数字特征）

    参数：
        datasets: 数据集名称
        numeric: 是否加载数字特征

    返回：
        同load_data，增加num_features
    """
    path = os.path.join(PROJECT_ROOT, "datasets", datasets, "")

    train_triples, train_adj, train_unique_entities = get_adj(path, "train")
    val_triples, val_adj, val_unique_entities = get_adj(path, "valid")
    test_triples, test_adj, test_unique_entities = get_adj(path, "test")

    entity2id = read_entity_from_id(path)
    relation2id = read_relation_from_id(path)

    img_features = torch.load(open(path + "img_features.pth", "rb"), weights_only=True)
    text_features = torch.load(
        open(path + "text_features.pth", "rb"), weights_only=True
    )

    if numeric:
        num_features = torch.load(
            open(path + "numeric_features.pth", "rb"), weights_only=True
        )
    else:
        num_features = None

    print(num_features)

    return (
        entity2id,
        relation2id,
        img_features,
        text_features,
        num_features,
        (train_triples, train_adj, train_unique_entities),
        (val_triples, val_adj, val_unique_entities),
        (test_triples, test_adj, test_unique_entities),
    )


def dataset_split(datasets):
    """
    划分训练/验证/测试集

    比例：训练90%，验证5%，测试5%（随机划分）
    """
    path = os.path.join(PROJECT_ROOT, "datasets", datasets, "")

    with open(path + datasets + "_EntityTriples.txt", "r") as f:
        triples = f.readlines()

    np.random.shuffle(triples)
    nb_val = round(0.05 * len(triples))
    nb_test = round(0.05 * len(triples))
    val_triples, test_triples, train_triples = (
        triples[:nb_val],
        triples[nb_val : nb_val + nb_test],
        triples[nb_val + nb_test :],
    )

    with open(path + "train.txt", "w") as f:
        f.writelines(train_triples)
    with open(path + "valid.txt", "w") as f:
        f.writelines(val_triples)
    with open(path + "test.txt", "w") as f:
        f.writelines(test_triples)


def data_loader(datasets):
    """
    简单的数据加载函数（用于调试）
    """
    path = os.path.join(PROJECT_ROOT, "datasets", datasets)
    with open(path + "/" + datasets + "_EntityTriples.txt", "r") as f:
        for line in f:
            print(line)
