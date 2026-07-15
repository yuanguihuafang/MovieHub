"""
Web演示界面 - Multi-MoE 多模态知识图谱推理系统

功能：
    - 展示模型性能指标
    - 快速评估模块（支持选择测试集、评估模式、样本数）
    - 数据探索（随机展示验证集样本）
    - 单样本验证（输入头实体+关系，预测尾实体）
"""

import sys
from pathlib import Path

# 与 eval/backend.py 一致：仓库根 + MMKG_item 根（满足 Multi_MoE 的 MMKG_item.* 与 models 导入）
_repo = Path(__file__).resolve().parent.parent.parent
_mmkg = Path(__file__).resolve().parent.parent
for _p in (_repo, _mmkg):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import gradio as gr
from backend import (
    load_model_and_data,  # 加载模型和数据
    evaluate_quick,  # 快速评估
    predict_tail,  # 单样本预测
    get_metrics,  # 获取性能指标
    get_valid_samples,  # 获取验证集样本
    get_model_info,  # 获取模型信息
    load_kg_eval_display_payload,  # 读取统一展示口径
    format_kg_eval_display_markdown,  # 渲染展示口径
)

# ============================================================
# 主程序入口
# ============================================================

if __name__ == "__main__":
    print("Multi-MoE 模型演示平台")
    print("=" * 50)

    # Step 1: 加载模型和数据
    print("[初始化] 正在加载模型和数据...")
    result = load_model_and_data(dataset="DB15K", use_cuda=False)
    if result is not True:
        print(f"❌ 加载失败: {result}")
        exit(1)

    # Step 2: 获取模型信息
    model_info = get_model_info()
    if model_info:
        print(f"   ✓ 实体数: {model_info['entity_count']:,}")
        print(f"   ✓ 关系数: {model_info['relation_count']:,}")

    # Step 3: 获取训练好的模型性能指标
    metrics = get_metrics()
    if metrics:
        print(
            f"   ✓ 模型性能: Hits@1={metrics['Hits@1'] * 100:.1f}%, MRR={metrics['MRR']:.4f}"
        )
        print(f"   ✓ 数据来源: {metrics.get('source')}")

    print("[启动] Gradio 界面...")

    # 获取初始验证集样本（用于页面初始化展示）
    initial_samples = get_valid_samples()

    # 读取与前端一致的“性能对比/指标展示”口径（如不存在则回退到硬编码/日志）
    kg_eval_payload = load_kg_eval_display_payload() or {}
    kg_eval_md = format_kg_eval_display_markdown(kg_eval_payload) if kg_eval_payload else ""
    kg_metrics = (kg_eval_payload.get("metrics") or {}) if kg_eval_payload else {}
    expected_perf_md = ""
    if kg_metrics:
        try:
            expected_perf_md = "\n".join(
                [
                    "（来自 `backend/data/eval/kg_eval_display.json` / 训练日志口径）",
                    f"- Hits@1: **{kg_metrics.get('Hits@1', 0) * 100:.2f}%** · Hits@3: **{kg_metrics.get('Hits@3', 0) * 100:.2f}%**",
                    "",
                    "> 💡 快速评估基于少量样本，结果可能与完整测试集有轻微偏差",
                ]
            )
        except Exception:
            expected_perf_md = ""

    # ============================================================
    # 构建Gradio界面
    # ============================================================

    with gr.Blocks(
        title="Multi-MoE 模型演示平台",
        theme=gr.themes.Soft(primary_hue="indigo"),
        css="""
        .gradio-container {max-width: 1400px !important;}
        """,
    ) as demo:
        # -------------------- 标题 --------------------
        gr.Markdown("# 🚀 Multi-MoE 多模态知识图谱推理系统")

        # -------------------- 模型基本信息 --------------------
        if model_info:
            gr.HTML(
                f"""
                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <strong>📊 数据集信息：</strong> DB15K &nbsp;&nbsp;
                    <strong>实体数：</strong> {model_info["entity_count"]:,} &nbsp;&nbsp;
                    <strong>关系数：</strong> {model_info["relation_count"]:,} &nbsp;&nbsp;
                    <strong>训练轮数：</strong> 2000 epochs
                </div>
                """
            )

        # -------------------- 性能指标卡片 + 技术亮点 --------------------
        with gr.Row():
            # 左侧：模型性能指标
            with gr.Column(scale=1):
                gr.Markdown("## 📊 模型性能指标（测试集）")
                if metrics:
                    gr.HTML(
                        f"""
                        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; text-align: center;">
                                <div>
                                    <div style="font-size: 0.9em; opacity: 0.85;">Hits@1</div>
                                    <div style="font-size: 2em; font-weight: bold;">{metrics["Hits@1"] * 100:.1f}%</div>
                                </div>
                                <div>
                                    <div style="font-size: 0.9em; opacity: 0.85;">Hits@3</div>
                                    <div style="font-size: 2em; font-weight: bold;">{metrics["Hits@3"] * 100:.1f}%</div>
                                </div>
                                <div>
                                    <div style="font-size: 0.9em; opacity: 0.85;">Hits@10</div>
                                    <div style="font-size: 2em; font-weight: bold;">{metrics["Hits@10"] * 100:.1f}%</div>
                                </div>
                                <div>
                                    <div style="font-size: 0.9em; opacity: 0.85;">MRR</div>
                                    <div style="font-size: 2em; font-weight: bold;">{metrics["MRR"]:.4f}</div>
                                </div>
                            </div>
                            <div style="margin-top: 15px; font-size: 0.85em; opacity: 0.85; text-align: center;">
                                📁 来源: {metrics.get("source", "训练日志")} &nbsp;&nbsp;|&nbsp;&nbsp; 📊 样本来源: {metrics["Total"]}
                            </div>
                        </div>
                        """
                    )
                else:
                    gr.Warning("未找到训练日志，请运行 `python train.py` 生成日志文件")

                # 消融实验结果
                gr.Markdown("### 📊 消融实验（100 轮快速验证）")
                gr.Markdown("#### 模态与 MoE 消融")
                gr.Markdown(
                    """
                    | 配置 | MRR | Hits@1 | Hits@10 | 参数量 |
                    | :--- | :---: | :---: | :---: | :---: |
                    | 仅结构（基线） | 0.1305 | 8.64% | 22.00% | — |
                    | 仅文本 | 0.1294 | 8.55% | 21.72% | — |
                    | 1 专家（无 MoE） | 0.1296 | 8.56% | — | 11.4M |
                    | **Full (S+I+T+F, 3专家)** | **0.3427** | **26.84%** | **48.51%** | **11.9M** |
                    """
                )

            # 右侧：技术亮点 + 性能对比
            with gr.Column(scale=1):
                gr.Markdown("## 🏆 技术亮点")
                gr.Markdown(
                    """
                    ### 🔥 核心创新
                    1. **多模态融合**：结构 + 图像 + 文本三模态联合学习
                    2. **MoE 门控**：自适应选择不同模态的专家组合
                    3. **四分支预测**：结构 / 图像 / 文本 / 融合 四视角互补
                    4. **端到端训练**：统一损失函数联合优化

                    ### ⚙️ 训练配置
                    - **优化器**: Adam (lr=0.0005)
                    - **正则化**: Dropout(0.3), weight_decay=1e-5
                    - **批次**: 1024, **负采样**: 2
                    - **GPU**: NVIDIA RTX PRO 6000
                    """
                )

                # 性能对比表格
                gr.Markdown("### 📈 性能对比（DB15K 测试集）")
                _baselines = kg_eval_payload.get("baselines", []) if kg_eval_payload else []
                _m = kg_metrics or {}
                if _m:
                    _h1 = _m.get("Hits@1", 0) * 100
                    _h3 = _m.get("Hits@3", 0) * 100
                    _md_lines = [
                        "| 模型 | Hits@1 | Hits@3 |",
                        "| :--- | :---: | :---: |",
                        f"| **Multi-MoE（本系统）** | **{_h1:.2f}%** | **{_h3:.2f}%** |",
                    ]
                    for b in _baselines:
                        bh1 = b.get("Hits@1", 0) * 100
                        bh3 = b.get("Hits@3", 0) * 100
                        _md_lines.append(f"| {b.get('name', 'Baseline')} | {bh1:.2f}% | {bh3:.2f}% |")
                    _md_lines.append("")
                    gr.Markdown("\n".join(_md_lines))
                else:
                    gr.Markdown("未找到评估数据，请确认 `backend/data/eval/kg_eval_display.json` 存在。")

        # -------------------- 快速评估模块 --------------------
        gr.Markdown("## ⚙️ 快速评估")
        gr.Markdown(
            """
            选择测试文件、评估参数后点击「开始评估」按钮，验证模型性能。
            
            **注意**：评估过程可能需要较长时间，建议先用小样本测试。
            """
        )

        with gr.Row():
            # 左侧：评估参数设置
            with gr.Column(scale=1):
                # 选择测试文件
                test_file_dropdown = gr.Dropdown(
                    choices=["valid.txt", "test.txt"],
                    value="test.txt",
                    label="测试文件",
                    info="选择要评估的数据集",
                )

                # 是否使用CUDA
                with gr.Row():
                    use_cuda_checkbox = gr.Checkbox(
                        label="使用 CUDA", value=False, info="启用GPU加速"
                    )

                # 评估模式
                eval_mode_radio = gr.Radio(
                    choices=["尾实体", "头实体", "双向评估"],
                    value="尾实体",
                    label="评估模式",
                    info="预测尾实体,预测头实体,双向评估",
                )

                # 样本数量滑块
                quick_samples_slider = gr.Slider(
                    minimum=10,
                    maximum=1000,
                    value=100,
                    step=10,
                    label="样本数量",
                    info="评估的样本条数（越多越准但越慢）",
                )

                # 评估按钮
                quick_btn = gr.Button("🚀 开始评估", variant="primary", size="lg")

                # 评估结果显示区
                quick_result = gr.Markdown(
                    label="评估结果", value="评估结果将在此显示..."
                )
                quick_log = gr.Textbox(
                    label="评估日志",
                    lines=6,
                    interactive=False,
                    placeholder="评估过程中的日志信息...",
                )

            # 右侧：评估说明
            with gr.Column(scale=1):
                gr.Markdown("### ℹ️ 评估说明")
                gr.Markdown(
                    """
                    **评估流程**：
                    1. 选择测试文件（valid.txt 或 test.txt）
                    2. 设置评估参数（CUDA、模式、样本数）
                    3. 点击「开始评估」按钮
                    4. 查看评估报告和过程日志
                    
                    **评估指标**：
                    - **MRR**：Mean Reciprocal Rank，平均倒数排名
                    - **Hits@1**：排名第一的正确率
                    - **Hits@3**：排名前三的正确率
                    - **Hits@10**：排名前十的正确率
                    
                    **注意事项**：
                    - ⚡ 使用 CUDA 可显著加速评估过程
                    - 🔍 评估时会自动过滤已知三元组
                    - 📊 样本数越多结果越准确，但耗时越长
                    - 🔄 支持双向评估（尾实体/头实体）
                    """
                )

                gr.Markdown("### 📈 预期性能")
                if expected_perf_md:
                    gr.Markdown(expected_perf_md)
                else:
                    gr.Markdown("预期性能将随训练日志变化。")

        # -------------------- 绑定快速评估事件 --------------------
        def on_quick_evaluate_click(test_file, use_cuda, eval_mode, samples):
            """
            快速评估按钮点击处理函数

            参数：
                test_file: 选中的测试文件
                use_cuda: 是否使用CUDA
                eval_mode: 评估模式（尾实体/头实体/双向）
                samples: 样本数量

            返回：
                (评估结果Markdown, 评估日志)
            """
            # 映射中文模式到英文
            mode_map = {"尾实体": "tail", "头实体": "head", "双向评估": "tail"}
            result = evaluate_quick(
                test_file, use_cuda, samples, mode_map.get(eval_mode, "tail")
            )
            if "error" in result:
                return f"❌ **错误：** {result['error']}", ""

            # 构建Markdown格式结果
            md = f"""## 📊 评估结果（{test_file}，前 {result["Total"]} 条，模式: {eval_mode}）

| 指标 | 值 |
| :--- | :--- |
| **Hits@1** | {result["Hits@1"]:.4f} ({result["Hits@1"] * 100:.2f}%) |
| **Hits@3** | {result["Hits@3"]:.4f} ({result["Hits@3"] * 100:.2f}%) |
| **Hits@10** | {result["Hits@10"]:.4f} ({result["Hits@10"] * 100:.2f}%) |
| **MRR** | {result["MRR"]:.4f} |

> 📊 数据来源: {test_file}
"""
            log = f"评估完成:\n  - 数据集: {test_file}\n  - 模式: {eval_mode}\n  - 样本数: {result['Total']}\n  - Hits@1: {result['Hits@1']:.4f}\n  - MRR: {result['MRR']:.4f}"
            return md, log

        # 绑定点击事件到处理函数
        quick_btn.click(
            fn=on_quick_evaluate_click,
            inputs=[
                test_file_dropdown,
                use_cuda_checkbox,
                eval_mode_radio,
                quick_samples_slider,
            ],
            outputs=[quick_result, quick_log],
        )

        # -------------------- 数据探索模块 --------------------
        gr.Markdown("## 📋 数据探索 ")

        with gr.Row():
            # 左侧：样本展示
            with gr.Column(scale=1):
                sample_btn = gr.Button("🔄 刷新样本", variant="secondary")
                sample_display = gr.Markdown(label="样本展示", value=initial_samples)

            # 右侧：数据集信息
            with gr.Column(scale=1):
                gr.Markdown("### 📊 数据集信息")
                gr.Markdown(
                    """
                    **DB15K 数据集**：
                    - 来源：DBpedia 多模态知识图谱
                    - 语言：英语（实体/关系URI）
                    - 模态：结构 + 图像 + 文本
                    
                    **文件说明**：
                    | 文件 | 用途 | 样本数 |
                    | :--- | :--- | :--- |
                    | train.txt | 训练集 | ~80k |
                    | valid.txt | 验证集 | ~10k |
                    | test.txt | 测试集 | ~10k |
                    
                    **三元组格式**（按TAB分隔）：
                    ```
                    <头实体URI>    <关系URI>    <尾实体URI>
                    ```
                    
                    **示例**：
                    ```
                    <http://dbpedia.org/resource/Apple_Inc.>    <http://dbpedia.org/ontology/founder>    <http://dbpedia.org/resource/Steve_Jobs>
                    ```
                    """
                )

        # -------------------- 单样本验证模块 --------------------
        gr.Markdown("## 🎯 单样本验证")
        gr.Markdown(
            "输入头实体和关系，预测尾实体（使用数据集中的实体/关系短名，如 `Apple_Inc.`, `founder`）"
        )

        with gr.Row():
            # 左侧：输入和预测
            with gr.Column(scale=1):
                # 头实体输入
                single_head = gr.Textbox(
                    label="头实体",
                    placeholder="例如: Apple_Inc., Microsoft, Google",
                    info="输入实体的短名（不区分大小写）",
                )

                # 关系输入
                single_rel = gr.Textbox(
                    label="关系",
                    placeholder="例如: founder, director, author",
                    info="输入关系的短名（如founder、director等）",
                )

                # Top-K设置
                with gr.Row():
                    single_topk = gr.Slider(
                        minimum=1,
                        maximum=20,
                        value=10,
                        step=1,
                        label="Top-K",
                        info="返回的候选数量",
                    )

                # 预测按钮
                single_predict_btn = gr.Button(
                    "🔍 开始预测", variant="secondary", size="lg"
                )

                # 预测结果显示
                single_result = gr.Markdown(
                    label="预测结果", value="预测结果将在此显示..."
                )
                single_log = gr.Textbox(
                    label="推理日志",
                    lines=4,
                    interactive=False,
                    placeholder="推理过程的详细日志...",
                )

            # 右侧：使用指南
            with gr.Column(scale=1):
                gr.Markdown("### ℹ️ 使用指南")
                gr.Markdown(
                    """
                    **输入格式**：
                    - **头实体**：实体短名（如 `Apple_Inc.`, `Bill_Gates`）
                    - **关系**：关系短名（如 `founder`, `director`, `author`）
                    
                    **输出说明**：
                    - 返回 Top-K 个候选尾实体
                    - 置信度基于模型预测分数（已过滤已知三元组）
                    - 排名按置信度降序排列
                    
                    **注意事项**：
                    - ⚠️ 仅支持 DB15K 数据集中的实体和关系
                    - 🔍 模糊匹配可用，但准确率有限
                    - 📊 推荐使用常见实体（如大公司、名人、电影）
                    """
                )

                gr.Markdown("### 📊 数据集统计")
                if model_info:
                    gr.Markdown(
                        f"""
                        - **实体总数**: {model_info["entity_count"]:,}
                        - **关系总数**: {model_info["relation_count"]:,}
                        - **训练集**: 79,222 条三元组
                        - **验证集**: 9,000+ 条三元组
                        - **测试集**: 9,000+ 条三元组
                        """
                    )
                else:
                    gr.Markdown("⚠️ 模型未加载")

        # -------------------- 绑定单样本预测事件 --------------------
        def on_single_predict(head, rel, topk):
            """
            单样本预测按钮点击处理函数

            参数：
                head: 头实体名称
                rel: 关系名称
                topk: 返回Top-K结果

            返回：
                (预测结果Markdown, 日志)
            """
            result = predict_tail(head, rel, topk)
            if "error" in result:
                return f"❌ {result['error']}", ""

            # 构建Markdown格式结果
            md = (
                "## 🔮 预测结果\n\n"
                f"**查询：** `({head}, {rel}, ?)`\n\n"
                "| 排名 | 尾实体 | 置信度 |\n"
                "| :--: | :------ | -----: |\n"
                + "\n".join(
                    f"| {r['rank']} | `{r['entity']}` | {r['score']:.4f} |"
                    for r in result["results"]
                )
                + "\n"
            )
            return md, "预测完成"

        # 绑定点击事件
        single_predict_btn.click(
            fn=on_single_predict,
            inputs=[single_head, single_rel, single_topk],
            outputs=[single_result, single_log],
        )

        # 绑定刷新样本事件
        sample_btn.click(fn=get_valid_samples, inputs=[], outputs=[sample_display])

    # -------------------- 启动Gradio服务 --------------------
    # server_name="0.0.0.0": 允许局域网访问
    # server_port=7860: 端口号
    # inbrowser=True: 启动后自动打开浏览器
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, inbrowser=True)
