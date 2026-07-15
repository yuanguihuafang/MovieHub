"""
各界面模块共用的路径、运行时缓存、静态映射与大模型客户端。

- LLM（对话/解释/偏好分解）：走 OPENAI_API_KEY + OPENAI_API_BASE_URL（OpenAI 兼容接口）
- Embedding（阿里 text-embedding-v3）：仅在需要 embedding 时走 DASHSCOPE_API_KEY
"""
import os
import sys

_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_backend_dir = os.path.dirname(_pkg_dir)
PROJECT_ROOT = os.path.dirname(_backend_dir)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import httpx
    from openai import OpenAI
    from dotenv import load_dotenv
except ImportError:
    raise ImportError("pip install openai httpx python-dotenv")

load_dotenv()
_root_env = os.path.join(PROJECT_ROOT, ".env")
if os.path.isfile(_root_env):
    load_dotenv(_root_env, override=True)

# ---- LLM client (OpenAI-compatible) ----
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_API_BASE_URL = (os.getenv("OPENAI_API_BASE_URL") or os.getenv("OPENAI_API_BASE") or "").strip()
_DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"

# 默认模型：供推荐链路的各类 LLM 调用复用
OPENAI_API_MODEL = (os.getenv("OPENAI_API_MODEL") or "").strip()
DEFAULT_LLM_MODEL = OPENAI_API_MODEL


def _http_trust_env_for_url(base_url: str, *, env_flag: str) -> bool:
    """
    是否让 httpx 继承系统代理（HTTP_PROXY/HTTPS_PROXY）。
    - 对 dashscope.aliyuncs.com：默认 False（国内直连更稳；Clash 代理偶发 SSL/连接错误）
    - 可用 OPENAI_HTTP_TRUST_ENV=1 / EMBEDDING_HTTP_TRUST_ENV=1 强制走代理
    """
    raw = (os.getenv(env_flag) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return "dashscope.aliyuncs.com" not in (base_url or "").lower()


def _openai_http_client(base_url: str, *, env_flag: str) -> httpx.Client:
    return httpx.Client(
        trust_env=_http_trust_env_for_url(base_url, env_flag=env_flag),
        timeout=httpx.Timeout(120.0, connect=45.0),
    )


_llm_base = OPENAI_API_BASE_URL or _DEFAULT_OPENAI_BASE
llm_client = (
    OpenAI(
        api_key=OPENAI_API_KEY,
        base_url=_llm_base,
        http_client=_openai_http_client(_llm_base, env_flag="OPENAI_HTTP_TRUST_ENV"),
    )
    if OPENAI_API_KEY
    else None
)

# ---- Embedding client (DashScope OpenAI-compatible) ----
DASHSCOPE_API_KEY = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
# 与 build_rag_database 入库向量须一致；可设环境变量 RAG_EMBEDDING_MODEL
RAG_EMBEDDING_MODEL = (os.getenv("RAG_EMBEDDING_MODEL") or "text-embedding-v3").strip()
_DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
embedding_client = (
    OpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url=_DASHSCOPE_BASE,
        http_client=_openai_http_client(_DASHSCOPE_BASE, env_flag="EMBEDDING_HTTP_TRUST_ENV"),
    )
    if DASHSCOPE_API_KEY
    else None
)

# 默认让 client 指向 llm_client（对话/解释主链路）
client = llm_client

_cache = {
    "model": None,
    "model_args": None,
    "entity2id": None,
    "relation2id": None,
    "id2entity": None,
    "id2relation": None,
    "entity_relations": None,
    "tail_relations": None,
    "movie_entities": None,
    "dataset": None,
    "chroma_collection": None,
    "douban_movies": None,
    "douban_genres": None,
    "tmdb_movies": None,
    "tmdb_genres": None,
    "tmdb_home_now_playing": None,
    "tmdb_home_upcoming": None,
    "tmdb_home_updated_at": None,
    "tmdb_home_error": None,
}

# ---- Chroma 向量库（全项目唯一配置源；相关代码分布见下，改路径/集合/模型只改此处）----
# build_rag_database.py  建库、embedding 入库（TMDB：RAG_TMDB_MIN_VOTE_AVERAGE，默认 4.0）
# recommender/recommend_rag.py  load_rag_db / rag_fetch_shared_vector_rows / rag_retrieve_for_kg_seeds / rag_llm_recommend / get_query_embedding
# recommender/recommend.py  _prefill_card_from_rag_chroma_meta（卡片补全）
# api/routers/admin.py      overview「RAG 已加载」← _cache["chroma_collection"]
# main.py                   startup → load_rag_db()
# requirements.txt          chromadb 版本锁定
#
# CHROMA_PERSIST_DIR（可选，写入 .env）：自定义 Chroma 持久化目录的绝对路径。
# Windows 若项目路径含中文且 HNSW 报 Cannot open header file，可设为纯英文路径（如 D:/chroma_mmkg），
# 建库与 main 须使用同一变量；建库前请先删该目录下旧库再全量写入。
_chroma_override = (os.getenv("CHROMA_PERSIST_DIR") or "").strip()
if _chroma_override:
    CHROMA_DIR = os.path.abspath(os.path.normpath(_chroma_override))
else:
    CHROMA_DIR = os.path.join(PROJECT_ROOT, "backend", "data", "RAG_data", "rag_db")
COLLECTION_NAME = "movies"

ALLOWED_GENRES = [
    "剧情",
    "喜剧",
    "爱情",
    "动作",
    "科幻",
    "悬疑",
    "动画",
    "纪录片",
    "战争",
    "奇幻",
]

GENRE_MAPPING = {
    "犯罪": "悬疑",
    "惊悚": "悬疑",
    "情色": "悬疑",
    "历史": "战争",
    "古装": "战争",
    "武侠": "战争",
    "冒险": "奇幻",
    "灾难": "奇幻",
    "西部": "奇幻",
    "传记": "剧情",
    "儿童": "剧情",
    "家庭": "剧情",
    "同性": "剧情",
    "歌舞": "剧情",
    "运动": "剧情",
    "音乐": "剧情",
    "恐怖": "悬疑",
}

MOVIE_GENRE_MAPPING = {
    "Science fiction": "科幻",
    "Thriller (genre)": "悬疑",
    "Crime fiction": "悬疑",
    "Detective fiction": "悬疑",
    "Space opera": "科幻",
    "Musical theatre": "剧情",
    "Comedy": "喜剧",
    "Romance": "爱情",
    "Action": "动作",
    "Drama": "剧情",
    "Horror": "悬疑",
    "Animation": "动画",
    "Adventure": "奇幻",
    "Fantasy": "奇幻",
    "Mystery": "悬疑",
    "War": "战争",
    "Western": "奇幻",
    "Documentary": "纪录片",
    "Biography": "剧情",
    "Historical": "战争",
    "Sci-Fi": "科幻",
    "Romantic comedy": "爱情",
    "Action comedy": "动作",
    "Crime drama": "悬疑",
    "Science fantasy": "科幻",
    "Superhero": "动作",
}

MOVIE_NAME_MAPPING = {
    "Inception": "盗梦空间",
    "Interstellar": "星际穿越",
    "The_Dark_Knight": "蝙蝠侠：黑暗骑士",
    "The_Lord_of_the_Rings": "指环王",
    "Titanic": "泰坦尼克号",
    "Avatar": "阿凡达",
    "The_Matrix": "黑客帝国",
    "Jurassic_Park": "侏罗纪公园",
    "Star_Wars": "星球大战",
    "The_Godfather": "教父",
    "Pulp_Fiction": "低俗小说",
    "Forrest_Gump": "阿甘正传",
    "The_Silence_of_the_Lambs": "沉默的羔羊",
    "Saving_Private_Ryan": "拯救大兵瑞恩",
    "Gladiator": "角斗士",
    "Braveheart": "勇敢的心",
    "The_Pianist": "钢琴家",
    "Schindler's_List": "辛德勒的名单",
    "The_Shawshank_Redemption": "肖申克的救赎",
    "The_Green_Mile": "绿里奇迹",
}

MOVIE_NAME_REVERSE_MAPPING = {v: k for k, v in MOVIE_NAME_MAPPING.items()}

# 豆瓣/用户常用中文名 -> DB15K 实体短名（URI 最后一段）。可按需扩充；优先 exact 命中。
KG_ENTITY_ALIASES = {
    "千与千寻": "Spirited_Away",
    "肖申克的救赎": "The_Shawshank_Redemption",
    "蝙蝠侠：黑暗骑士": "The_Dark_Knight_(film)",
    "黑暗骑士": "The_Dark_Knight_(film)",
    "泰坦尼克号": "Titanic_(1997_film)",
    "阿凡达": "Avatar_(2009_film)",
    "盗梦空间": "Inception",
    "黑客帝国": "The_Matrix",
    "星球大战": "Star_Wars",
    "侏罗纪公园": "Jurassic_Park_(film)",
    "低俗小说": "Pulp_Fiction",
    "辛德勒的名单": "Schindler's_List",
    "拯救大兵瑞恩": "Saving_Private_Ryan",
    "沉默的羔羊": "The_Silence_of_the_Lambs_(film)",
    "阿甘正传": "Forrest_Gump",
    "绿里奇迹": "The_Green_Mile_(film)",
    "角斗士": "Gladiator_(2000_film)",
    "勇敢的心": "Braveheart",
    "钢琴家": "The_Pianist_(2002_film)",
}

DOUBAN_FIELD_MAPPING = {
    "title": "电影名称",
    "score": "评分",
    "rank": "排名",
    "run_time": "时长",
    "start_time": "上映日期",
    "type": "类型",
    "director": "导演",
    "actor": "演员",
    "area": "地区",
    "language": "语言",
    "comment_num": "评论数",
}

# 与 DB15K relation2id.txt 中 URI 最后一段一致（如 ontology/director → director）
RELATION_WEIGHTS = {
    "genre": 3.0,
    "director": 2.5,
    "starring": 2.0,
    "related": 1.85,
    "subsequentWork": 1.65,
    "previousWork": 1.65,
    "basedOn": 1.45,
    "producer": 1.5,
    "writer": 1.0,
    "country": 1.0,
    "language": 1.0,
    "musicComposer": 0.85,
    "award": 0.95,
    "cinematography": 0.75,
    "editing": 0.75,
    "narrator": 0.7,
    "musicSubgenre": 0.85,
    "musicFusionGenre": 0.85,
    # DB15K 中电影链路常见补充关系（用于提升冷启动召回）
    "distributor": 1.35,
    "executiveProducer": 1.25,
    "creator": 1.1,
}

RELATION_ZH = {
    "director": "导演",
    "starring": "主演",
    "genre": "类型",
    "producer": "制片人",
    "country": "国家",
    "language": "语言",
    "musicComposer": "配乐",
    "writer": "编剧",
    "distributor": "发行方",
    "executiveProducer": "执行制片",
    "creator": "创作者",
}

# MOE_RELATION_* 均须在 relation2id 可解析；见 MMKG_item/datasets/DB15K/relation2id.txt
MOE_RELATION_CORE = ("genre", "director", "starring")
MOE_RELATION_FILL = (
    "subsequentWork",
    "previousWork",
    "basedOn",
    "related",
    "writer",
    "producer",
    "musicComposer",
    "country",
    "language",
    "award",
    "cinematography",
    "editing",
    "narrator",
    "musicSubgenre",
    "musicFusionGenre",
    "distributor",
    "executiveProducer",
    "creator",
)

# 从电影实体出发、边指向的非电影尾实体（演员/导演等），可作中间种子参与 MoE，再预测其它电影
MOE_INTERMEDIATE_FROM_MOVIE_RELATIONS = frozenset(
    {
        "starring",
        "director",
        "writer",
        "producer",
        "musicComposer",
        "narrator",
        "cinematography",
        "editing",
        "award",
        "executiveProducer",
        "creator",
    }
)
