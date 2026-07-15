"""
Multi-MoE模型 - 多模态知识图谱混合专家模型

模型架构：
    1. 三种嵌入：
        - 结构嵌入（entity_embeddings）
        - 图像嵌入（img_entity_embeddings）
        - 文本嵌入（txt_entity_embeddings）

    2. 四个MoE专家层：
        - structure_moe: 处理结构嵌入
        - visual_moe: 处理图像嵌入
        - text_moe: 处理文本嵌入
        - mm_moe: 处理融合嵌入

    3. 两个融合层：
        - fuse_e: 实体多模态融合
        - fuse_r: 关系多模态融合

    4. 四分支预测：
        - 结构预测 (pred_s)
        - 图像预测 (pred_i)
        - 文本预测 (pred_d)
        - 融合预测 (pred_mm)
"""
from MMKG_item.layers.layer1_moe import *
from MMKG_item.layers.layer2_fuse import *
from .model import BaseModel

class Multi_MoE(BaseModel):
    """
    多模态MoE知识图谱模型

    特点：
        - 三模态输入：结构、图像、文本
        - MoE门控：自适应选择专家组合
        - 四分支预测：结构/图像/文本/融合
    """

    def __init__(self, args):
        """
        初始化Multi-MoE模型

        参数：
            args:
                - entity2id: 实体ID映射
                - dim: 结构嵌入维度
                - r_dim: 关系嵌入维度
                - img: 图像特征张量
                - desp: 文本特征张量
                - n_exp: MoE专家数量
                - dataset: 数据集名称
                - device: 计算设备
        """
        super(Multi_MoE, self).__init__(args)
        self.dim = args.dim
        self.device = args.device

        # ==================== 1. 结构嵌入 ====================
        # 实体嵌入
        self.entity_embeddings = nn.Embedding(
            len(args.entity2id), args.dim, padding_idx=None
        )
        nn.init.xavier_normal_(self.entity_embeddings.weight)

        # 关系嵌入（包含逆关系，所以是2倍）
        self.relation_embeddings = nn.Embedding(
            2 * len(args.relation2id), args.r_dim, padding_idx=None
        )
        nn.init.xavier_normal_(self.relation_embeddings.weight)

        # ==================== 2. 图像和文本特征预处理 ====================
        # 图像特征池化：从64x64降到16x16（降维）
        if args.dataset == "DB15K":
            img_pool = torch.nn.AvgPool2d(4, stride=4)
            img = img_pool(args.img.to(self.device).view(-1, 64, 64))
            img = img.view(img.size(0), -1)

            # 文本特征池化：从12x64降到4x64
            txt_pool = torch.nn.AdaptiveAvgPool2d(output_size=(4, 64))
            txt = txt_pool(args.desp.to(self.device).view(-1, 12, 64))
            txt = txt.view(txt.size(0), -1)

        # ==================== 3. 图像嵌入 ====================
        # ps:区分CV训练的模型是为了得出图像embedding，而这里的图像embedding作为一个最底层存储embedding层，用于三元组对应匹配
        # 这几块儿一直都是拿到图像embedding，不涉及到图像embedding的CV模型
        # 图像实体嵌入（使用预提取特征，可微调）
        self.img_entity_embeddings = nn.Embedding.from_pretrained(img, freeze=False)
        # 图像关系嵌入（随机初始化）
        self.img_relation_embeddings = nn.Embedding(
            2 * len(args.relation2id), args.r_dim, padding_idx=None
        )
        nn.init.xavier_normal_(self.img_relation_embeddings.weight)

        # ==================== 4. 文本嵌入 ====================
        self.txt_entity_embeddings = nn.Embedding.from_pretrained(txt, freeze=False)
        self.txt_relation_embeddings = nn.Embedding(
            2 * len(args.relation2id), args.r_dim, padding_idx=None
        )
        nn.init.xavier_normal_(self.txt_relation_embeddings.weight)

        # ==================== 5. MoE专家层 ====================
        self.dim = args.dim
        self.img_dim = self.img_entity_embeddings.weight.data.shape[1]
        self.txt_dim = self.txt_entity_embeddings.weight.data.shape[1]
        self.fuse_out_dim = self.dim

        # 四个MoE专家
        self.visual_moe = MoEAdaptorLayer(
            n_exps=args.n_exp, layers=[self.img_dim, self.img_dim]
        )
        self.text_moe = MoEAdaptorLayer(
            n_exps=args.n_exp, layers=[self.txt_dim, self.txt_dim]
        )
        self.structure_moe = MoEAdaptorLayer(
            n_exps=args.n_exp, layers=[self.dim, self.dim]
        )
        self.mm_moe = MoEAdaptorLayer(
            n_exps=args.n_exp, layers=[self.fuse_out_dim, self.fuse_out_dim]
        )

        # ==================== 6. 多模态融合层 ====================
        self.fuse_e = ModalFusionLayer(
            in_dim=args.dim,
            out_dim=self.fuse_out_dim,
            multi=2,
            img_dim=self.img_dim,
            txt_dim=self.txt_dim,
        )
        self.fuse_r = ModalFusionLayer(
            in_dim=args.r_dim,
            out_dim=self.fuse_out_dim,
            multi=2,
            img_dim=args.r_dim,
            txt_dim=args.r_dim,
        )

        # ==================== 7. 损失函数 ====================
        self.bias = nn.Parameter(torch.zeros(len(args.entity2id)))
        self.bceloss = nn.BCELoss()

    def forward(self, batch_inputs, adj):
        """
        前向传播

        参数：
            batch_inputs: [batch_size, 3] 三元组索引 [头, 关系, 尾]
            adj: 邻接矩阵（可选）

        返回：
            output: [pred_s, pred_i, pred_d, pred_mm] 四个分支的预测分数
            embeddings: 训练时返回解纠缠嵌入，推理时返回注意力权重
        """
        # 提取头实体和关系
        head = batch_inputs[:, 0]
        relation = batch_inputs[:, 1]

        # ==================== 1. 获取三种嵌入 ====================
        # 结构嵌入
        stru_head = self.entity_embeddings(head)
        # 图像嵌入
        img_head = self.img_entity_embeddings(head)
        # 文本嵌入
        txt_head = self.txt_entity_embeddings(head)

        # ==================== 2. MoE专家处理 ====================
        e_embed, disen_str, atten_s = self.structure_moe(stru_head)
        e_img_embed, disen_img, atten_i = self.visual_moe(img_head)
        e_txt_embed, disen_txt, atten_t = self.text_moe(txt_head)

        # 关系嵌入
        r_embed = self.relation_embeddings(relation)
        r_img_embed = r_embed
        r_txt_embed = r_embed

        # ==================== 3. 多模态自适应融合 ====================
        e_mm_embed, attn_f = self.fuse_e(e_embed, e_img_embed, e_txt_embed)
        r_mm_embed, _ = self.fuse_r(r_embed, r_img_embed, r_txt_embed)

        # ==================== 4. 计算四个分支的预测分数 ====================
        pred_s = e_embed * r_embed
        pred_i = e_img_embed * r_img_embed
        pred_d = e_txt_embed * r_txt_embed
        # 融合预测：融合嵌入 * 融合关系嵌入
        pred_mm = e_mm_embed * r_mm_embed

        # ==================== 5. 与所有实体计算得分 ====================
        all_s = self.entity_embeddings.weight # [all_entity,dim]  -> [dim,all_entity]
        all_v = self.img_entity_embeddings.weight
        all_t = self.txt_entity_embeddings.weight
        all_f, _ = self.fuse_e(all_s, all_v, all_t) # [num,dim]

        # 矩阵乘法计算每个实体的得分
        pred_s = torch.mm(pred_s, all_s.transpose(1, 0)) #[b,num]
        pred_i = torch.mm(pred_i, all_v.transpose(1, 0)) #[b,num]
        pred_d = torch.mm(pred_d, all_t.transpose(1, 0)) #[b,num]
        pred_mm = torch.mm(pred_mm, all_f.transpose(1, 0)) #[b,num]

        # Sigmoid激活
        pred_s = torch.sigmoid(pred_s) #[b,num]
        pred_i = torch.sigmoid(pred_i) #[b,num]
        pred_d = torch.sigmoid(pred_d) #[b,num]
        pred_mm = torch.sigmoid(pred_mm) #[b,num]

        # 训练模式 vs 推理模式
        if not self.training:
            # 推理模式：返回注意力权重（用于分析）
            return [pred_s, pred_i, pred_d, pred_mm], [atten_s,atten_i,atten_t,attn_f,]
        else:
            # 训练模式：返回解纠缠嵌入（用于对比学习）
            return [pred_s, pred_i, pred_d, pred_mm], [disen_str, disen_img, disen_txt]

    def get_batch_embeddings(self, batch_inputs):
        """
        获取批次嵌入（用于分析或对比学习）

        参数：
            batch_inputs: [batch_size, 3] 三元组

        返回：
            [disen_str, disen_img, disent_txt] 三种解纠缠嵌入
        """
        head = batch_inputs[:, 0]
        _, disen_str, _ = self.structure_moe(self.entity_embeddings(head))
        _, disen_img, _ = self.visual_moe(self.img_entity_embeddings(head))
        _, disen_txt, _ = self.text_moe(self.txt_entity_embeddings(head))
        return [disen_str, disen_img, disen_txt]

    def loss_func(self, output, target):
        """
        计算四分支损失之和

        参数：
            output: [pred_s, pred_i, pred_d, pred_mm] 四个预测
            target: 真实标签

        返回：
            loss: 四个分支损失之和
        """
        loss_s = self.bceloss(output[0], target)
        loss_i = self.bceloss(output[1], target)
        loss_d = self.bceloss(output[2], target)
        loss_mm = self.bceloss(output[3], target)
        return loss_s + loss_i + loss_d + loss_mm
