# -*- coding: utf-8 -*-
"""命令行冒烟：python -m backend.recommender（需在项目根目录且 PYTHONPATH 含项目根）。"""
from backend.recommender import load_douban_data, load_kg_model, load_rag_db, recommend_for_user

if __name__ == "__main__":
    print("=" * 50)
    print("  🎬 MovieHub 推荐系统冒烟测试")
    print("=" * 50)

    print("\n📦 [1/3] 加载知识图谱模型...")
    result = load_kg_model("DB15K")
    if result is True:
        print("✅ [1/3] 知识图谱加载完成")
    else:
        print(f"❌ [1/3] 知识图谱加载失败: {result}")

    print("📦 [2/3] 加载 RAG 向量数据库...")
    result = load_rag_db()
    if result is True:
        print("✅ [2/3] RAG 数据库加载完成")
    else:
        print(f"❌ [2/3] RAG 数据库加载失败: {result}")

    print("📦 [3/3] 加载豆瓣数据...")
    load_douban_data()
    print("✅ [3/3] 豆瓣数据加载完成")

    print("\n🎬 生成推荐...")
    result = recommend_for_user(
        user_id=1,
        user_input="推荐一些像《泰坦尼克号》一样感人的爱情电影",
        favorite_movies=[],
        watched_items=[],
        history_genres=[],
        topk_kg=8,
        topk_rag=6,
        with_llm_explain=False,
    )

    if result["success"]:
        print("✅ 推荐成功！")
        print(result["recommend_text"][:500])
    else:
        print(f"❌ 推荐失败: {result['error']}")

    print("\n✅ 测试完成！")
