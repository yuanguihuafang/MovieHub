import argparse
import os
import sys
import time
import numpy as np
import torch

_repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
from tqdm import tqdm
from models.Multi_MoE import *
from models.model import *
from utils.data_loader import *
from utils.data_util import load_data

####################################1、定义训练需要的参数####################################
def parse_args():
    config_args = {
        # 模型训练参数
        "epochs": 2000,  # 训练轮数
        "eval_freq": 100,  # 评估频率（每多少轮评估一次）
        "decoder_save_model": "./checkpoint/DB15K/trained_model.pth",  # 模型保存路径
        # 模型结构参数
        "dim": 256,  # 实体嵌入维度
        "r_dim": 256,  # 关系嵌入维度
        "layer_nums": 4,  # 层数
        "n_exp": 3,  # MoE专家数量
        # 训练参数
        "batch_size": 1024,  # 批次大小
        "lr": 0.0005,  # 学习率
        "weight_decay": 0,  # 权重衰减（L2正则化）
        "weight_decay_gat": 1e-5,  # GAT模块的权重衰减
        "gamma": 1.0,  # 学习率衰减因子
        "patience": 5,  # 早停耐心值
        "lr_reduce_freq": 500,  # 学习率降低频率
        # Dropout参数
        "dropout_gat": 0.3,  # GAT模块dropout
        "dropout": 0.3,  # 模型dropout
        # 多模态特征参数
        "img_dim": 256,  # 图像特征维度
        "txt_dim": 256,  # 文本特征维度
        # 其他参数
        "mu": 0.0001,  # 正则化系数
        "seed": 10010,  # 随机种子（保证可复现性）
        "cuda": 0,  # CUDA设备ID（-1为CPU）
        "save": 1,  # 是否保存模型
        # 模型选择（手动切换注释即可）
        "num-layers": 3,  # 卷积层数
        "k_w": 16,  # 卷积核宽度
        "k_h": 16,  # 卷积核高度
        "n_heads": 2,  # 注意力头数
        "dataset": "DB15K",  # 数据集名称
        "encoder": 0,  # 编码器类型
        "image_features": 1,  # 是否使用图像特征
        "text_features": 1,  # 是否使用文本特征
        "neg_num": 2,  # 负样本数量
        "neg_num_gat": 2,  # GAT负样本数量
        "alpha": 0.2,  # LeakyReLU斜率
        "alpha_gat": 0.2,  # GAT LeakyReLU斜率
        "out_channels": 32,  # 卷积输出通道数
        "kernel_size": 3,  # 卷积核大小
        "bias": 1,  # 是否使用偏置
    }

    parser = argparse.ArgumentParser()
    # 将config_args中的参数添加到命令行解析器
    for param, val in config_args.items():
        parser.add_argument(f"--{param}", default=val, type=type(val))
    args = parser.parse_args()
    return args


# 解析参数并打印
args = parse_args()
for k, v in list(vars(args).items()):
    print(str(k) + ":" + str(v))

# 设置随机种子，确保实验可复现
np.random.seed(args.seed)
torch.manual_seed(args.seed)

# 检查并设置计算设备（GPU/CPU）
if torch.cuda.is_available() and int(args.cuda) >= 0:
    args.device = "cuda:" + str(args.cuda)
    print(f"Using: {args.device}")
    torch.cuda.set_device(int(args.cuda))
else:
    args.device = "cpu"
    print(f"Using: {args.device}")
    print("CUDA is not available, using CPU instead")


####################################2、加载数据集#######################################################
# 数据加载流程：
# 1. 从文件加载三元组数据（训练/验证/测试集）
# 2. 加载实体/关系ID映射
# 3. 加载预提取的图像和文本特征
# 返回：
#   entity2id: 实体到ID的映射字典
#   relation2id:关系到ID的映射字典
#   img_features: 图像特征矩阵
#   text_features: 文本特征矩阵
#   train_data: 训练数据（三元组列表、邻接矩阵、唯一实体集合）
#   val_data: 验证数据
#   test_data: 测试数据
entity2id, relation2id, img_features, text_features, train_data, val_data, test_data = (
    load_data(args.dataset)
)
print("Training data {:04d}".format(len(train_data[0])))

# 5. 创建语料库对象（将数据封装为可迭代的批次形式）
corpus = ConvECorpus(args, train_data, val_data, test_data, entity2id, relation2id)

# 6. 特征归一化处理
# 对预提取的多模态特征进行L2归一化，提高训练稳定性
if args.image_features:
    args.img = F.normalize(torch.Tensor(img_features), p=2, dim=1)
if args.text_features:
    args.desp = F.normalize(torch.Tensor(text_features), p=2, dim=1)

# 将实体/关系映射保存到args中，便于模型使用
args.entity2id = entity2id
args.relation2id = relation2id


def train_decoder(args):
    """
    训练解码器（模型）的主函数

    流程：
        1. 初始化模型（Multi_MoE）
        2. 设置优化器和学习率调度器
        3. 执行多轮训练（epochs）
        4. 定期评估模型性能
        5. 保存最佳模型
    """

    ####################################3、定义模型及其组件#######################################################
    # 选择模型：可切换TransE、IKRL等基线模型
    model = Multi_MoE(args)
    # model = BaselineWrapper(TransE(args))
    # model = BaselineWrapper(IKRL(args))

    # 更新参数中的图像和文本维度（由模型实际输出决定）
    args.img_dim = model.img_dim
    args.txt_dim = model.txt_dim

    # 打印模型结构
    print(str(model))

    # 优化器：Adam优化器
    # params: 模型所有可训练参数
    # lr: 初始学习率
    # weight_decay: L2正则化（默认0，本项目未使用）
    optimizer = torch.optim.Adam(
        params=model.parameters(), lr=args.lr, weight_decay=args.weight_decay
    )

    # 学习率调度器：指数衰减
    # gamma: 衰减因子，每轮将学习率乘以gamma
    lr_scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer, args.gamma)

    # 计算模型总参数量
    tot_params = sum([np.prod(p.size()) for p in model.parameters()])
    print(f"Total number of parameters: {tot_params}")

    # 将模型移动到指定设备（GPU/CPU）
    if args.cuda is not None and int(args.cuda) >= 0:
        model = model.to(args.device)

    #################################### 4、训练模型#######################################################
    t_total = time.time()  # 记录总开始时间

    # 初始化最佳指标字典（用于保存最佳验证/测试结果）
    best_val_metrics = model.init_metric_dict()
    best_test_metrics = model.init_metric_dict()

    # 设置批次大小
    corpus.batch_size = args.batch_size

    # 训练循环：遍历所有epochs
    training_range = tqdm(range(args.epochs), desc="Training")
    for epoch in training_range:
        model.train()  # 设置为训练模式（启用dropout等）
        epoch_loss = []  # 记录本轮损失

        # 打乱训练数据顺序
        corpus.shuffle()

        # 遍历所有批次
        for batch_num in range(corpus.max_batch_num):
            # 清空梯度（每次迭代前必须）
            optimizer.zero_grad()

            # 获取本批次数据
            # train_indices: [batch_size, 3] 三元组索引（头、关系、尾-1）
            # train_values: [batch_size, num_entities] 标签矩阵（正样本位置为1）
            train_indices, train_values = corpus.get_batch(batch_num)
            train_indices = torch.LongTensor(train_indices)

            # 将数据移动到设备
            if args.cuda is not None and int(args.cuda) >= 0:
                train_indices = train_indices.to(args.device)
                train_values = train_values.to(args.device)

            # 前向传播
            # output: [pred_s, pred_i, pred_d, pred_mm] 四个分支的预测分数
            # embeddings: 解纠缠的嵌入向量（训练时disen，推理时atten）
            output, embeddings = model.forward(train_indices, corpus.train_adj_matrix)

            # 计算损失：四个分支损失之和
            # loss_s: 结构分支损失
            # loss_i: 图像分支损失
            # loss_d: 文本分支损失
            # loss_mm: 多模态融合分支损失
            loss = model.loss_func(output, train_values)

            # 反向传播：计算梯度
            loss.backward()

            # 更新参数
            optimizer.step()

            # 记录本批次损失
            epoch_loss.append(loss.data.item())

        # 每轮结束后更新学习率
        lr_scheduler.step()

        #################################### 5、评估模型#######################################################
        # 按照eval_freq指定的频率进行评估
        if (epoch + 1) % args.eval_freq == 0:
            print(
                "Epoch数量 {:04d} , 平均损失 {:.4f} \n".format(
                    epoch + 1, sum(epoch_loss) / len(epoch_loss)
                )
            )
            training_range.set_postfix(loss="main: {:.5} ".format(sum(epoch_loss)))

            model.eval()  # 设置为评估模式
            print(
                "==================================第",
                (epoch + 1) // args.eval_freq,
                "次评估========================================",
            )

            # 在测试集上进行评估
            with torch.no_grad():
                val_metrics = corpus.get_validation_pred(model, "test")[0]

            # 更新最佳测试指标
            if val_metrics["MRR"] > best_test_metrics["MRR"]:
                best_test_metrics["MRR"] = val_metrics["MRR"]
            if val_metrics["MR"] < best_test_metrics["MR"]:
                best_test_metrics["MR"] = val_metrics["MR"]
            if val_metrics["Hits@1"] > best_test_metrics["Hits@1"]:
                best_test_metrics["Hits@1"] = val_metrics["Hits@1"]
            if val_metrics["Hits@3"] > best_test_metrics["Hits@3"]:
                best_test_metrics["Hits@3"] = val_metrics["Hits@3"]
            if val_metrics["Hits@10"] > best_test_metrics["Hits@10"]:
                best_test_metrics["Hits@10"] = val_metrics["Hits@10"]
            if val_metrics["Hits@100"] > best_test_metrics["Hits@100"]:
                best_test_metrics["Hits@100"] = val_metrics["Hits@100"]

            # 打印评估结果
            print(
                "\n".join(
                    [
                        "Epoch: {:04d}".format(epoch + 1),
                        model.format_metrics(val_metrics, "test"),
                    ]
                )
            )
            print("\n\n")

    print("Total time elapsed: {:.4f}s".format(time.time() - t_total))

    # 如果best_test_metrics为空，将最后一次评估结果作为最佳结果
    if not best_test_metrics:
        model.eval()
        with torch.no_grad():
            best_test_metrics = corpus.get_validation_pred(model, "test")

    # 打印最终结果
    print(
        "\n".join(["Val set results:", model.format_metrics(best_val_metrics, "val")])
    )
    print(
        "\n".join(
            ["Test set results:", model.format_metrics(best_test_metrics, "test")]
        )
    )
    print("\n\n\n")

    # 保存模型
    if args.save:
        torch.save(model.state_dict(), args.decoder_save_model)
        print("Saved model!")


if __name__ == "__main__":
    train_decoder(args)
