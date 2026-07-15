"""
Multi-MoE 消融实验运行器

使用方式：
    python MMKG_item/ablation/ablation_runner.py --quick          # 快速验证（100 epochs）
    python MMKG_item/ablation/ablation_runner.py                  # 完整实验（2000 epochs）
    python MMKG_item/ablation/ablation_runner.py --group modality # 只跑模态消融
    python MMKG_item/ablation/ablation_runner.py --group moe      # 只跑 MoE 专家数消融
    python MMKG_item/ablation/ablation_runner.py --group branch   # 只跑单分支评估
    python MMKG_item/ablation/ablation_runner.py --epochs 500     # 自定义轮数
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F

# 确保项目根在 sys.path
_repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from MMKG_item.ablation.ablation_models import Multi_MoE_Ablation, ABLATION_CONFIGS
from MMKG_item.utils.data_loader import ConvECorpus
from MMKG_item.utils.data_util import load_data
from tqdm import tqdm


# ============================================================
# 参数解析
# ============================================================
def parse_args():
    parser = argparse.ArgumentParser(description="Multi-MoE 消融实验")
    parser.add_argument("--quick", action="store_true", help="快速验证模式（100 epochs）")
    parser.add_argument("--epochs", type=int, default=None, help="训练轮数（默认 2000）")
    parser.add_argument("--group", type=str, default="all",
                        choices=["all", "modality", "moe", "branch"],
                        help="要运行的实验组")
    parser.add_argument("--eval_freq", type=int, default=100, help="评估频率")
    parser.add_argument("--batch_size", type=int, default=1024, help="批大小")
    parser.add_argument("--lr", type=float, default=0.0005, help="学习率")
    parser.add_argument("--cuda", type=int, default=0, help="CUDA 设备（-1 为 CPU）")
    parser.add_argument("--seed", type=int, default=10010, help="随机种子")
    parser.add_argument("--dataset", type=str, default="DB15K", help="数据集名称")
    parser.add_argument("--dim", type=int, default=256, help="嵌入维度")
    parser.add_argument("--r_dim", type=int, default=256, help="关系嵌入维度")
    parser.add_argument("--dropout", type=float, default=0.3, help="Dropout")
    parser.add_argument("--save_dir", type=str, default="./MMKG_item/ablation/checkpoint",
                        help="消融模型保存目录")
    parser.add_argument("--results_dir", type=str, default="./MMKG_item/ablation/log",
                        help="消融结果保存目录（JSON/Markdown）")
    parser.add_argument("--checkpoint", type=str,
                        default="./MMKG_item/checkpoint/DB15K/trained_model.pth",
                        help="已训练的 Full 模型路径（branch 模式用）")
    return parser.parse_args()


# ============================================================
# 构建训练用 args 对象（兼容 Multi_MoE 的接口）
# ============================================================
def build_model_args(base_args):
    """构建传递给模型的参数对象"""
    class Args:
        pass
    a = Args()
    a.dim = base_args.dim
    a.r_dim = base_args.r_dim
    a.n_exp = getattr(base_args, "_n_exp", 3)  # 可被实验配置覆盖
    a.dataset = base_args.dataset
    a.device = base_args.device
    a.dropout = base_args.dropout
    a.entity2id = base_args.entity2id
    a.relation2id = base_args.relation2id
    a.img = base_args.img
    a.desp = base_args.desp
    return a


# ============================================================
# 对已有 checkpoint 只做评估（不训练）
# ============================================================
def evaluate_existing_checkpoint(exp_name, exp_config, base_args, corpus):
    """加载已有 checkpoint 并评估，返回与 run_single_experiment 相同格式的结果"""
    print(f"\n{'='*70}")
    print(f"  实验: {exp_name} — 加载已有 checkpoint，仅评估")
    print(f"{'='*70}")

    base_args._n_exp = exp_config.get("n_exp", 3)
    model_args = build_model_args(base_args)
    model = Multi_MoE_Ablation(
        model_args,
        use_image=exp_config["use_image"],
        use_text=exp_config["use_text"],
        use_fusion=exp_config["use_fusion"],
    )

    ckpt_path = os.path.join(base_args.save_dir, f"{exp_name}.pth")
    model.load_state_dict(torch.load(ckpt_path, map_location=base_args.device))
    if base_args.device != "cpu":
        model = model.to(base_args.device)
    model.eval()

    total_params = int(sum(np.prod(p.size()) for p in model.parameters()))

    eval_branch = exp_config.get("eval_branch", -1)
    with torch.no_grad():
        if eval_branch == -1:
            metrics, _ = corpus.get_validation_pred(model, "test")
        else:
            metrics, _ = corpus.get_validation_pred_signle(model, "test", index=eval_branch)

    print(f"  结果: MRR={metrics['MRR']:.4f}  Hits@1={metrics['Hits@1']:.4f}  "
          f"Hits@3={metrics['Hits@3']:.4f}  Hits@10={metrics['Hits@10']:.4f}  "
          f"MR={metrics['MR']:.1f}")

    return {
        "name": exp_name,
        "desc": exp_config.get("desc", ""),
        "group": exp_config.get("group", ""),
        "config": {
            "use_image": exp_config["use_image"],
            "use_text": exp_config["use_text"],
            "use_fusion": exp_config["use_fusion"],
            "n_exp": exp_config.get("n_exp", 3),
            "eval_branch": exp_config.get("eval_branch", -1),
        },
        "best_metrics": metrics,
        "branch_metrics": {},
        "elapsed_s": 0,
        "total_params": total_params,
    }


# ============================================================
# 单次实验的训练 + 评估
# ============================================================
def run_single_experiment(exp_name, exp_config, base_args, corpus):
    """
    运行单个消融实验

    参数：
        exp_name: 实验名称
        exp_config: 实验配置 dict（来自 ABLATION_CONFIGS）
        base_args: 全局参数
        corpus: ConvECorpus 数据加载器

    返回：
        dict: {"name", "config", "best_metrics", "branch_metrics", "elapsed", "params"}
    """
    print(f"\n{'='*70}")
    print(f"  实验: {exp_name} — {exp_config.get('desc', '')}")
    print(f"  image={exp_config['use_image']}, text={exp_config['use_text']}, "
          f"fusion={exp_config['use_fusion']}, n_exp={exp_config.get('n_exp', 3)}")
    print(f"{'='*70}")

    # 设置 n_exp（MoE 消融实验会覆盖）
    base_args._n_exp = exp_config.get("n_exp", 3)

    # 创建模型
    model_args = build_model_args(base_args)
    model = Multi_MoE_Ablation(
        model_args,
        use_image=exp_config["use_image"],
        use_text=exp_config["use_text"],
        use_fusion=exp_config["use_fusion"],
    )

    if base_args.device != "cpu":
        model = model.to(base_args.device)

    # 优化器
    optimizer = torch.optim.Adam(model.parameters(), lr=base_args.lr)
    lr_scheduler = torch.optim.lr_scheduler.ExponentialLR(optimizer, gamma=1.0)

    # 参数量
    total_params = sum(np.prod(p.size()) for p in model.parameters())

    # 训练
    best_metrics = model.init_metric_dict()
    corpus.batch_size = base_args.batch_size
    epochs = base_args.epochs

    t_start = time.time()
    training_range = tqdm(range(epochs), desc=f"[{exp_name}]", leave=True)

    for epoch in training_range:
        model.train()
        epoch_loss = []
        corpus.shuffle()

        for batch_num in range(corpus.max_batch_num):
            optimizer.zero_grad()
            train_indices, train_values = corpus.get_batch(batch_num)
            train_indices = torch.LongTensor(train_indices)

            if base_args.device != "cpu":
                train_indices = train_indices.to(base_args.device)
                train_values = train_values.to(base_args.device)

            output, embeddings = model.forward(train_indices, corpus.train_adj_matrix)
            loss = model.loss_func(output, train_values)

            loss.backward()
            optimizer.step()
            epoch_loss.append(loss.data.item())

        lr_scheduler.step()

        # 定期评估
        if (epoch + 1) % base_args.eval_freq == 0:
            avg_loss = sum(epoch_loss) / len(epoch_loss)
            training_range.set_postfix(loss=f"{avg_loss:.5f}")

            model.eval()
            with torch.no_grad():
                # eval_branch 控制评估方式
                eval_branch = exp_config.get("eval_branch", -1)
                if eval_branch == -1:
                    # 默认：四分支平均
                    val_metrics, _ = corpus.get_validation_pred(model, "test")
                else:
                    # 单分支评估
                    val_metrics, _ = corpus.get_validation_pred_signle(model, "test", index=eval_branch)

            # 更新最佳指标
            for key in ["MRR", "Hits@1", "Hits@3", "Hits@10", "Hits@100"]:
                if val_metrics[key] > best_metrics[key]:
                    best_metrics[key] = val_metrics[key]
            if val_metrics["MR"] < best_metrics["MR"]:
                best_metrics["MR"] = val_metrics["MR"]

    elapsed = time.time() - t_start

    # ---- 单分支评估（对 Full 模型训练完成后）----
    branch_metrics = {}
    group = exp_config.get("group", "")
    if group == "modality" and exp_name == "Full":
        print(f"\n  >> Full 模型单分支评估...")
        model.eval()
        branch_names = ["pred_s (结构)", "pred_i (图像)", "pred_d (文本)", "pred_mm (融合)", "平均"]
        with torch.no_grad():
            for idx, bname in enumerate(branch_names):
                if idx < 4:
                    m, _ = corpus.get_validation_pred_signle(model, "test", index=idx)
                else:
                    m, _ = corpus.get_validation_pred(model, "test")
                branch_metrics[bname] = m
                print(f"     {bname}: MRR={m['MRR']:.4f}  Hits@1={m['Hits@1']:.4f}  "
                      f"Hits@3={m['Hits@3']:.4f}  Hits@10={m['Hits@10']:.4f}")

    # 保存模型
    save_dir = base_args.save_dir
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, f"{exp_name}.pth")
    torch.save(model.state_dict(), save_path)

    result = {
        "name": exp_name,
        "desc": exp_config.get("desc", ""),
        "group": exp_config.get("group", ""),
        "config": {
            "use_image": exp_config["use_image"],
            "use_text": exp_config["use_text"],
            "use_fusion": exp_config["use_fusion"],
            "n_exp": exp_config.get("n_exp", 3),
            "eval_branch": exp_config.get("eval_branch", -1),
        },
        "best_metrics": best_metrics,
        "branch_metrics": branch_metrics,
        "elapsed_s": round(elapsed, 1),
        "total_params": int(total_params),
    }

    print(f"\n  结果: MRR={best_metrics['MRR']:.4f}  Hits@1={best_metrics['Hits@1']:.4f}  "
          f"Hits@3={best_metrics['Hits@3']:.4f}  Hits@10={best_metrics['Hits@10']:.4f}  "
          f"MR={best_metrics['MR']:.1f}  耗时={elapsed:.1f}s")

    return result


# ============================================================
# 结果输出
# ============================================================
def print_results_table(results, group_name):
    """打印 Markdown 格式的结果表格"""
    print(f"\n\n{'='*70}")
    print(f"  {group_name} — 结果汇总")
    print(f"{'='*70}\n")

    header = f"| {'实验':<20} | {'MRR':>8} | {'Hits@1':>8} | {'Hits@3':>8} | {'Hits@10':>8} | {'Hits@100':>8} | {'MR':>10} | {'耗时(s)':>8} |"
    sep    = f"|{'-'*22}|{'-'*10}|{'-'*10}|{'-'*10}|{'-'*10}|{'-'*10}|{'-'*12}|{'-'*10}|"
    print(header)
    print(sep)
    for r in results:
        m = r["best_metrics"]
        row = (f"| {r['name']:<20} | {m['MRR']:>8.4f} | {m['Hits@1']:>8.4f} | "
               f"{m['Hits@3']:>8.4f} | {m['Hits@10']:>8.4f} | {m['Hits@100']:>8.4f} | "
               f"{m['MR']:>10.1f} | {r['elapsed_s']:>8.1f} |")
        print(row)
    print()


def save_results(all_results, save_dir):
    """保存结果到 JSON 和 Markdown 文件（增量合并，不覆盖旧数据）"""
    os.makedirs(save_dir, exist_ok=True)

    # JSON — 先加载已有结果，按 name 合并
    json_path = os.path.join(save_dir, "ablation_results.json")
    merged = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                for r in json.load(f):
                    merged[r["name"]] = r
        except Exception:
            pass
    for r in all_results:
        merged[r["name"]] = r
    merged_list = list(merged.values())

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(merged_list, f, ensure_ascii=False, indent=2)
    print(f"  JSON 结果已保存: {json_path}")

    # Markdown（论文友好格式）— 基于合并后的完整数据生成
    md_path = os.path.join(save_dir, "ablation_results.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Multi-MoE 消融实验结果\n\n")
        f.write(f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # A. 模态消融
        modality_results = [r for r in merged_list if r["group"] == "modality"]
        if modality_results:
            f.write("## A. 模态消融实验\n\n")
            f.write("| 模型配置 | MRR | Hits@1 | Hits@3 | Hits@10 | Hits@100 | MR |\n")
            f.write("|----------|-----|--------|--------|---------|----------|----|\n")
            for r in modality_results:
                m = r["best_metrics"]
                f.write(f"| {r['desc']} | {m['MRR']:.4f} | {m['Hits@1']:.4f} | "
                        f"{m['Hits@3']:.4f} | {m['Hits@10']:.4f} | {m['Hits@100']:.4f} | {m['MR']:.1f} |\n")
            f.write("\n")

        # B. MoE 专家数消融
        moe_results = [r for r in merged_list if r["group"] == "moe"]
        if moe_results:
            f.write("## B. MoE 专家数消融实验\n\n")
            f.write("| 专家数 | MRR | Hits@1 | Hits@3 | Hits@10 | Hits@100 | MR | 参数量 |\n")
            f.write("|--------|-----|--------|--------|---------|----------|----|----|\n")
            for r in moe_results:
                m = r["best_metrics"]
                f.write(f"| {r['desc']} | {m['MRR']:.4f} | {m['Hits@1']:.4f} | "
                        f"{m['Hits@3']:.4f} | {m['Hits@10']:.4f} | {m['Hits@100']:.4f} | "
                        f"{m['MR']:.1f} | {r['total_params']:,} |\n")
            f.write("\n")

        # C. 单分支评估
        branch_results = [r for r in merged_list if r["group"] == "branch"]
        if branch_results:
            f.write("## C. 单分支评估（Full 模型）\n\n")
            f.write("| 预测分支 | MRR | Hits@1 | Hits@3 | Hits@10 | Hits@100 | MR |\n")
            f.write("|----------|-----|--------|--------|---------|----------|----|\n")
            for r in branch_results:
                m = r["best_metrics"]
                f.write(f"| {r['desc']} | {m['MRR']:.4f} | {m['Hits@1']:.4f} | "
                        f"{m['Hits@3']:.4f} | {m['Hits@10']:.4f} | {m['Hits@100']:.4f} | {m['MR']:.1f} |\n")
            f.write("\n")

        # Full 模型的单分支详细数据（如果有）
        full_result = next((r for r in merged_list if r["name"] == "Full"), None)
        if full_result and full_result.get("branch_metrics"):
            f.write("### Full 模型各分支详细指标\n\n")
            f.write("| 分支 | MRR | Hits@1 | Hits@3 | Hits@10 | Hits@100 | MR |\n")
            f.write("|------|-----|--------|--------|---------|----------|----|\n")
            for bname, bm in full_result["branch_metrics"].items():
                f.write(f"| {bname} | {bm['MRR']:.4f} | {bm['Hits@1']:.4f} | "
                        f"{bm['Hits@3']:.4f} | {bm['Hits@10']:.4f} | {bm['Hits@100']:.4f} | {bm['MR']:.1f} |\n")
            f.write("\n")

    print(f"  Markdown 结果已保存: {md_path}")


# ============================================================
# 主入口
# ============================================================
def main():
    args = parse_args()

    # 确定 epochs
    if args.quick:
        args.epochs = 100
        args.eval_freq = 50
        print(">>> 快速验证模式：epochs=100, eval_freq=50")
    elif args.epochs is None:
        args.epochs = 2000
    print(f">>> 训练轮数: {args.epochs}, 评估频率: {args.eval_freq}")

    # 设置随机种子
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    # 设备
    if torch.cuda.is_available() and args.cuda >= 0:
        args.device = f"cuda:{args.cuda}"
        torch.cuda.set_device(args.cuda)
    else:
        args.device = "cpu"
    print(f">>> 设备: {args.device}")

    # 加载数据（只加载一次）
    print("\n>>> 加载数据集...")
    entity2id, relation2id, img_features, text_features, train_data, val_data, test_data = (
        load_data(args.dataset)
    )
    print(f"    实体数: {len(entity2id)}, 关系数: {len(relation2id)}, "
          f"训练三元组: {len(train_data[0])}")

    corpus = ConvECorpus(args, train_data, val_data, test_data, entity2id, relation2id)

    # 特征归一化
    args.img = F.normalize(torch.Tensor(img_features), p=2, dim=1)
    args.desp = F.normalize(torch.Tensor(text_features), p=2, dim=1)
    args.entity2id = entity2id
    args.relation2id = relation2id

    # 筛选要运行的实验
    if args.group == "all":
        experiments = {k: v for k, v in ABLATION_CONFIGS.items() if v.get("group") != "branch"}
    else:
        experiments = {k: v for k, v in ABLATION_CONFIGS.items() if v.get("group") == args.group}

    # branch 组：加载已训练的 Full 模型，评估各分支
    if args.group == "branch":
        print(f"\n>>> 分支评估模式：加载已有 Full 模型，评估各分支...")
        print(f"    Checkpoint: {args.checkpoint}")

        # 计算参数量
        tmp_model = Multi_MoE_Ablation(
            build_model_args(args),
            use_image=True, use_text=True, use_fusion=True,
        )
        total_params = int(sum(np.prod(p.size()) for p in tmp_model.parameters()))
        del tmp_model

        # 加载训练好的 Full 模型
        full_model = Multi_MoE_Ablation(
            build_model_args(args),
            use_image=True, use_text=True, use_fusion=True,
        )
        full_model.load_state_dict(
            torch.load(args.checkpoint, map_location=args.device)
        )
        if args.device != "cpu":
            full_model = full_model.to(args.device)
        full_model.eval()

        all_results = []
        branch_experiments = {k: v for k, v in experiments.items() if v.get("group") == "branch"}
        with torch.no_grad():
            for exp_name, exp_config in branch_experiments.items():
                eval_branch = exp_config["eval_branch"]
                print(f"\n  评估分支: {exp_name} — {exp_config['desc']}")
                if eval_branch == -1:
                    metrics, _ = corpus.get_validation_pred(full_model, "test")
                else:
                    metrics, _ = corpus.get_validation_pred_signle(full_model, "test", index=eval_branch)

                all_results.append({
                    "name": exp_name,
                    "desc": exp_config.get("desc", ""),
                    "group": "branch",
                    "config": {"eval_branch": eval_branch},
                    "best_metrics": metrics,
                    "branch_metrics": {},
                    "elapsed_s": 0,
                    "total_params": total_params,
                })
                print(f"     MRR={metrics['MRR']:.4f}  Hits@1={metrics['Hits@1']:.4f}  "
                      f"Hits@3={metrics['Hits@3']:.4f}  Hits@10={metrics['Hits@10']:.4f}")

        save_results(all_results, args.results_dir)

    else:
        # 如果主 checkpoint 存在但消融目录下没有 Full.pth，自动复制
        main_ckpt = args.checkpoint
        full_ablation_ckpt = os.path.join(args.save_dir, "Full.pth")
        if os.path.exists(main_ckpt) and not os.path.exists(full_ablation_ckpt):
            import shutil
            shutil.copy2(main_ckpt, full_ablation_ckpt)
            print(f">>> 已复制主 checkpoint 到消融目录: {full_ablation_ckpt}")

        # 同理，MoE_3experts 和 Full 配置相同（n_exp=3），也可以复用
        moe3_ablation_ckpt = os.path.join(args.save_dir, "MoE_3experts.pth")
        if os.path.exists(main_ckpt) and not os.path.exists(moe3_ablation_ckpt):
            import shutil
            shutil.copy2(main_ckpt, moe3_ablation_ckpt)
            print(f">>> 已复制主 checkpoint 到消融目录: {moe3_ablation_ckpt}")

        # 加载已有结果（如有），用于跳过已训练的实验
        existing_results = {}
        existing_json = os.path.join(args.results_dir, "ablation_results.json")
        if os.path.exists(existing_json):
            try:
                with open(existing_json, "r", encoding="utf-8") as f:
                    for r in json.load(f):
                        existing_results[r["name"]] = r
                print(f">>> 发现已有结果文件，将跳过已训练的实验")
            except Exception:
                pass

        # 将实验分为三类：跳过、仅评估、需训练
        skip_names = []       # 有 checkpoint + 有结果 → 直接复用
        eval_names = []       # 有 checkpoint + 无结果 → 仅评估
        train_exps = {}       # 无 checkpoint → 完整训练

        for exp_name, exp_config in experiments.items():
            ckpt_path = os.path.join(args.save_dir, f"{exp_name}.pth")
            if exp_name in existing_results and os.path.exists(ckpt_path):
                skip_names.append(exp_name)
            elif os.path.exists(ckpt_path):
                eval_names.append(exp_name)
            else:
                train_exps[exp_name] = exp_config

        if skip_names:
            print(f">>> 跳过（已有结果）: {', '.join(skip_names)}")
        if eval_names:
            print(f">>> 仅评估（已有 checkpoint）: {', '.join(eval_names)}")
        if train_exps:
            print(f">>> 需要训练: {', '.join(train_exps.keys())}")
        if not eval_names and not train_exps:
            print(f">>> 所有实验均已完成，无需重新训练")

        all_results = [existing_results[name] for name in skip_names]

        # 仅评估已有 checkpoint
        for exp_name in eval_names:
            exp_config = experiments[exp_name]
            result = evaluate_existing_checkpoint(exp_name, exp_config, args, corpus)
            all_results.append(result)
            save_results(all_results, args.results_dir)

        # 完整训练
        for exp_name, exp_config in train_exps.items():
            result = run_single_experiment(exp_name, exp_config, args, corpus)
            all_results.append(result)
            save_results(all_results, args.results_dir)

            # 增量保存（防止中途断电丢失）
            save_results(all_results, args.results_dir)

    # 打印汇总表格
    groups_seen = set(r["group"] for r in all_results)
    for group in ["modality", "moe", "branch"]:
        if group in groups_seen:
            group_results = [r for r in all_results if r["group"] == group]
            group_labels = {
                "modality": "A. 模态消融", "moe": "B. MoE 专家数消融",
                "branch": "C. 单分支评估",
            }
            print_results_table(group_results, group_labels[group])

    # 最终保存
    save_results(all_results, args.results_dir)
    print(f"\n>>> 所有实验完成！")
    print(f"    模型目录: {args.save_dir}")
    print(f"    结果目录: {args.results_dir}")


if __name__ == "__main__":
    main()
