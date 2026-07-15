"""DB15K 知识图谱加载、实体匹配与 Multi_MoE 链路预测。"""
import hashlib
import json
import os
import re
import threading
import time
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Dict, Optional, Set, Tuple

# 防止 PyTorch OpenMP 与 Python ThreadPoolExecutor 冲突导致原生层崩溃
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import torch

# 模型推理锁：防止并发 forward 导致原生层 0xC0000409 崩溃
_model_inference_lock = threading.Lock()

from MMKG_item.models.Multi_MoE import Multi_MoE
from MMKG_item.utils.data_util import load_data

from backend.recommender.common import (
    ALLOWED_GENRES,
    KG_ENTITY_ALIASES,
    MOE_INTERMEDIATE_FROM_MOVIE_RELATIONS,
    MOE_RELATION_CORE,
    MOE_RELATION_FILL,
    MOVIE_NAME_REVERSE_MAPPING,
    PROJECT_ROOT,
    RELATION_WEIGHTS,
    _cache,
)


def _load_db15k_movie_lexicon() -> dict[str, str]:
    """加载离线电影词典（alias -> DB15K 电影实体短名）。"""
    cached = _cache.get("db15k_movie_lexicon")
    if isinstance(cached, dict):
        return cached
    p = os.path.join(PROJECT_ROOT, "backend", "data", "kg", "db15k_movie_lexicon.json")
    out: dict[str, str] = {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        mp = (data or {}).get("alias_to_entity") or {}
        if isinstance(mp, dict):
            for k, v in mp.items():
                ks = str(k).strip().lower()
                vs = str(v).strip()
                if ks and vs:
                    out[ks] = vs
    except Exception:
        out = {}
    _cache["db15k_movie_lexicon"] = out
    return out


def _norm_flat_lookup_key(s: str) -> str:
    """与 entity2id URI 尾段对应的短名，做数据集内规范化键（不含模型推理）。"""
    s = (s or "").strip()
    s = s.replace("（", "(").replace("）", ")")
    s = re.sub(r"\s+", " ", s.lower().replace("_", " ").replace("-", " ").replace(".", ""))
    return s.strip()


def _tokens_from_entity_short(short: str) -> list[str]:
    """从 DB15K 实体短名抽取英文检索词（与 MMKG_item/data_util 中 URI 最后一段一致）。"""
    b = re.sub(r"_\(\d{4}_film\)$", "", short, flags=re.I)
    b = re.sub(r"_\(film\)$", "", b, flags=re.I)
    b = re.sub(r"_\(movie\)$", "", b, flags=re.I)
    raw = b.replace("_", " ")
    toks = re.split(r"[^a-z0-9]+", raw.lower())
    return [t for t in toks if len(t) >= 3]


def build_kg_movie_resolution_index(movie_entities: set[str]) -> dict[str, dict]:
    """
    仅基于训练集识别出的电影实体短名（entity2id URI 尾段）建表：
    - lookup：多种规范化拼写 -> 规范短名
    - token_index：英文词 -> 候选电影实体列表

    对齐 MMKG_item 训练数据中的实体命名，不依赖全表 SequenceMatcher 式「模糊模型」。
    """
    lookup: dict[str, str] = {}
    token_index: dict[str, list[str]] = defaultdict(list)

    def put_key(k: str, canonical: str) -> None:
        if not k or len(k.strip()) < 2:
            return
        kl = k.strip().lower()
        if kl not in lookup:
            lookup[kl] = canonical
        nf = _norm_flat_lookup_key(k)
        if nf and nf not in lookup:
            lookup[nf] = canonical

    for s in sorted(movie_entities):
        put_key(s, s)
        if "_" in s:
            put_key(s.replace("_", " "), s)
        b = re.sub(r"_\(\d{4}_film\)$", "", s, flags=re.I)
        b = re.sub(r"_\(film\)$", "", b, flags=re.I)
        b = re.sub(r"_\(movie\)$", "", b, flags=re.I)
        if b and b != s:
            put_key(b, s)
        for tok in _tokens_from_entity_short(s):
            lst = token_index[tok]
            if len(lst) < 120 and (not lst or lst[-1] != s):
                lst.append(s)

    return {"lookup": lookup, "token_index": dict(token_index)}


def find_entity_in_kg(name: str):
    """
    在 DB15K 中匹配 **训练数据 entity2id 中的电影实体短名**（URI 最后一段，与 MMKG_item/utils/data_util.load_data 一致）。

    顺序：KG_ENTITY_ALIASES / 精确与变体 → _(film) 候选打分 → 子串（数据集内电影实体）→
    **预建 lookup 与英文词倒排索引**（仅 movie_entities，无全表 SequenceMatcher 相似度扫描）。

    中文片名仍依赖 common.KG_ENTITY_ALIASES / MOVIE_NAME_* 映射到英文短名后再命中数据集。
    """
    entity2id = _cache.get("entity2id", {})
    movie_entities = _cache.get("movie_entities", set())
    short_set = _cache.get("entity_short_set")
    if not entity2id:
        return None
    if short_set is None:
        short_set = {k.rstrip(">").rsplit("/", 1)[-1] for k in entity2id.keys()}
        _cache["entity_short_set"] = short_set

    raw = (name or "").strip().strip("《》").strip()
    if not raw:
        return None
    raw = raw.replace("（", "(").replace("）", ")")

    if raw in KG_ENTITY_ALIASES:
        raw = KG_ENTITY_ALIASES[raw]
    if raw in MOVIE_NAME_REVERSE_MAPPING:
        raw = MOVIE_NAME_REVERSE_MAPPING[raw]

    # 优先使用离线词典（DB15K 电影别名 -> 规范短名）
    # 只作为候选，最终仍要求命中数据集 short_set
    lex = _load_db15k_movie_lexicon()
    if lex:
        k1 = raw.strip().lower()
        k2 = _norm_flat_lookup_key(raw)
        lx = lex.get(k1) or lex.get(k2)
        if lx and lx in short_set and (not movie_entities or lx in movie_entities):
            return lx

    def _norm(s: str) -> str:
        return s.lower().replace("_", " ").replace("-", " ").replace(".", "")

    def _extract_year(s: str) -> Optional[int]:
        for m in re.finditer(r"(?<![0-9])(19|20)\d{2}(?![0-9])", s):
            try:
                return int(m.group(0))
            except ValueError:
                pass
        return None

    def _try_short(sl: str) -> Optional[str]:
        if not sl:
            return None
        if sl in short_set:
            return sl
        sln = sl.lower()
        snorm = _norm(sl)
        for s in short_set:
            if s.lower() == sln:
                return s
        for s in short_set:
            if _norm(s) == snorm:
                return s
        return None

    def _film_disamb_suffix_candidates(title_base: str) -> list[str]:
        if not title_base:
            return []
        tb = title_base.strip()
        out: list[str] = []
        pref = tb + "_("
        for s in short_set:
            if s == tb:
                out.append(s)
                continue
            if s.startswith(pref):
                low = s.lower()
                if "film" in low or "movie" in low:
                    out.append(s)
        return out

    def _pick_best_film(
        cands: list[str], *, year_hint: Optional[int], hint_for_sim: str
    ) -> Optional[str]:
        if not cands:
            return None
        uniq = list(dict.fromkeys(cands))
        h = hint_for_sim.lower().strip()
        h_norm = _norm(hint_for_sim)

        def score(s: str) -> float:
            sc = 0.0
            if s in movie_entities:
                sc += 80.0
            low = s.lower()
            if year_hint and re.search(rf"_\({year_hint}_film\)\s*$", s):
                sc += 60.0
            if low.endswith("_(film)") or low.endswith("_(movie)"):
                sc += 25.0
            elif "_film)" in low or "_movie)" in low:
                sc += 15.0
            if "airbender" in low or "last_airbender" in low:
                sc -= 40.0
            sc += SequenceMatcher(None, h, low.replace("_", " ")).ratio() * 12.0
            if h_norm and _norm(s).startswith(h_norm):
                sc += 8.0
            return sc

        return max(uniq, key=score)

    variants: list[str] = []
    seen: set[str] = set()

    def _add(v: str) -> None:
        v = v.strip()
        if v and v not in seen:
            seen.add(v)
            variants.append(v)

    _add(raw)
    if " " in raw and "_" not in raw and re.search(r"[A-Za-z]", raw):
        _add(re.sub(r"\s+", "_", raw.strip()))
    base = re.sub(r"_\(\d{4}_film\)$", "", raw)
    base = re.sub(r"_\(film\)$", "", base, flags=re.I)
    base = re.sub(r"_\(movie\)$", "", base, flags=re.I)
    if base != raw:
        _add(base)
    if re.match(r"^[A-Za-z0-9_\s',&:-]+$", raw) or "_" in raw:
        b_ = base.replace(" ", "_")
        if b_.lower().startswith("the_") and len(b_) > 4:
            _add(b_[4:])
        elif b_ and not b_.lower().startswith("the_"):
            _add("The_" + b_)
    if "(" not in raw:
        _add(raw + "_(film)")
        _add(raw + "_(movie)")

    year_hint = _extract_year(raw)

    for cand in variants:
        hit = _try_short(cand)
        if hit:
            return hit

    title_bases: set[str] = set()
    for v in variants:
        b = re.sub(r"_\(\d{4}_film\)$", "", v)
        b = re.sub(r"_\(film\)$", "", b, flags=re.I)
        b = re.sub(r"_\(movie\)$", "", b, flags=re.I)
        b = b.strip()
        if b:
            title_bases.add(b)
            if b.lower().startswith("the_") and len(b) > 4:
                title_bases.add(b[4:])
            elif b and re.match(r"^[A-Za-z]", b):
                title_bases.add("The_" + b)

    film_cands: list[str] = []
    for tb in title_bases:
        film_cands.extend(_film_disamb_suffix_candidates(tb))
    picked = _pick_best_film(film_cands, year_hint=year_hint, hint_for_sim=raw)
    if picked:
        return picked

    name_lower = raw.lower().strip()
    name_norm = _norm(raw)
    sub_cands: list[str] = []
    _min_sub = 2 if re.search(r"[\u4e00-\u9fff]", raw) else 3
    if len(name_lower) >= _min_sub:
        for short in movie_entities:
            sl = short.lower()
            if name_lower in sl or sl in name_lower:
                sub_cands.append(short)
            elif name_norm and _norm(short) == name_norm:
                sub_cands.append(short)
    sub_pick = _pick_best_film(sub_cands, year_hint=year_hint, hint_for_sim=raw)
    if sub_pick:
        return sub_pick

    # 数据集内检索：由 load_kg_model 预建的 lookup / 词索引（entity2id 电影实体），不用全表相似度模糊匹配
    idx_pack = _cache.get("kg_movie_resolution") or {}
    lookup = idx_pack.get("lookup") or {}
    token_index = idx_pack.get("token_index") or {}

    def _try_ds_lookup(strings: list[str]) -> Optional[str]:
        for x in strings:
            if not x:
                continue
            xs = x.strip()
            if xs.lower() in lookup:
                hit = lookup[xs.lower()]
                if hit in movie_entities:
                    return hit
            nf = _norm_flat_lookup_key(xs)
            if nf in lookup:
                hit = lookup[nf]
                if hit in movie_entities:
                    return hit
        return None

    ds = _try_ds_lookup([*variants, *[b for b in title_bases if b]])
    if ds:
        return ds

    qtok: set[str] = set()
    for v in variants[:16]:
        qtok.update(_tokens_from_entity_short(v.replace(" ", "_")))
    qtok.update(_tokens_from_entity_short(raw.replace(" ", "_")))
    for w in re.findall(r"[A-Za-z]{3,}", raw):
        qtok.add(w.lower())
    if qtok and token_index:
        votes: dict[str, int] = defaultdict(int)
        for t in qtok:
            for ent in token_index.get(t, [])[:80]:
                votes[ent] += 1
        if votes:
            top_sc = max(votes.values())
            tops = [e for e, c in votes.items() if c == top_sc]
            if top_sc >= 2:
                picked2 = _pick_best_film(tops[:16], year_hint=year_hint, hint_for_sim=raw)
                if picked2:
                    return picked2
            if top_sc == 1 and len(tops) == 1:
                return tops[0]

    return None


def load_kg_model(dataset_name: str = "DB15K", verbose: bool = True):
    """加载知识图谱模型和数据"""
    try:
        start = time.time()
        if verbose:
            print("📦 [KG] 正在加载数据集...")

        dataset = load_data(dataset_name)
        (
            entity2id,
            relation2id,
            img_emb,
            text_emb,
            train_data,
            val_data,
            test_data,
        ) = dataset

        train_triples = train_data[0]
        train_adj_tuple = train_data[1]
        valid_triples = val_data[0]
        test_triples = test_data[0]

        adj_indices = torch.LongTensor([train_adj_tuple[0], train_adj_tuple[1]])
        adj_values = torch.LongTensor(train_adj_tuple[2])

        id2entity = {v: k for k, v in entity2id.items()}
        id2relation = {v: k for k, v in relation2id.items()}

        movie_entities = set()
        entity_relations = defaultdict(list)
        tail_relations = defaultdict(list)
        all_entities = set()

        for h, r, t in train_triples + valid_triples + test_triples:
            h_entity = id2entity.get(h, "")
            r_relation = id2relation.get(r, "")
            t_entity = id2entity.get(t, "")

            if h_entity and t_entity and r_relation:
                h_short = h_entity.rstrip(">").rsplit("/", 1)[-1]
                t_short = t_entity.rstrip(">").rsplit("/", 1)[-1]
                r_short = r_relation.rstrip(">").rsplit("/", 1)[-1]

                if r_short in RELATION_WEIGHTS:
                    entity_relations[h_short].append((r_short, t_short))
                    tail_relations[(h_short, r_short)].append(t_short)
                    all_entities.add(h_short)
                    all_entities.add(t_short)

        directors_and_actors = set()
        for h_entity in entity_relations:
            for r, t in entity_relations[h_entity]:
                if r in ["director", "starring"]:
                    directors_and_actors.add(t)

        _film_rel_core = frozenset(
            {
                "director",
                "starring",
                "genre",
                "producer",
                "writer",
                "musicComposer",
                "cinematography",
                "editing",
                "distributor",
                "executiveProducer",
                "creator",
            }
        )

        for entity in all_entities:
            if entity in directors_and_actors:
                continue

            el = entity.lower()
            if "(film)" in el or "(movie)" in el:
                movie_entities.add(entity)
            elif entity in entity_relations:
                rel_types = {
                    r
                    for r, t in entity_relations[entity]
                    if r in _film_rel_core
                }
                strong_roles = {"director", "starring", "producer", "writer"}
                weak_roles = {
                    "genre",
                    "musicComposer",
                    "cinematography",
                    "editing",
                    "distributor",
                    "executiveProducer",
                    "creator",
                }
                if rel_types.intersection(strong_roles) and rel_types.intersection(weak_roles):
                    movie_entities.add(entity)

        if verbose:
            print(
                f"   电影实体: {len(movie_entities)} 个，总实体: {len(all_entities)} 个"
            )

        if verbose:
            print("📦 [KG] 正在加载模型...")

        entity_num = len(entity2id)
        relation_num = len(relation2id)
        emb_dim = 256
        img_dim = img_emb.shape[1] if img_emb is not None else 0
        text_dim = text_emb.shape[1] if text_emb is not None else 0

        class ModelArgs:
            def __init__(
                self,
                entity2id,
                relation2id,
                dim,
                r_dim,
                img,
                desp,
                n_exp,
                dataset,
                device,
            ):
                self.entity2id = entity2id
                self.relation2id = relation2id
                self.dim = dim
                self.r_dim = r_dim
                self.img = img
                self.desp = desp
                self.n_exp = n_exp
                self.dataset = dataset
                self.device = device

        img_emb_tensor = img_emb["embeddings"] if isinstance(img_emb, dict) else img_emb
        text_emb_tensor = (
            text_emb["embeddings"] if isinstance(text_emb, dict) else text_emb
        )

        try:
            kg_n_exp = int((os.getenv("KG_N_EXP") or "3").strip())
        except ValueError:
            kg_n_exp = 3
        if kg_n_exp < 1:
            kg_n_exp = 3

        args = ModelArgs(
            entity2id=entity2id,
            relation2id=relation2id,
            dim=emb_dim,
            r_dim=emb_dim,
            img=img_emb_tensor,
            desp=text_emb_tensor,
            n_exp=kg_n_exp,
            dataset=dataset_name,
            device=torch.device("cpu"),
        )

        model = Multi_MoE(args)

        model_path = os.path.join(
            PROJECT_ROOT, "MMKG_item", "checkpoint", dataset_name, "trained_model.pth"
        )
        if os.path.exists(model_path):
            try:
                state_dict = torch.load(
                    model_path, map_location=torch.device("cpu"), weights_only=True
                )
                model.load_state_dict(state_dict, strict=False)
                model.eval()
            except Exception as e:
                if verbose:
                    msg = str(e)
                    print(f"❌ [KG] 加载预训练模型失败: {msg[:120]}")
                    if "size mismatch" in msg.lower() and "gate" in msg.lower():
                        print(
                            f"   提示: n_exp 不一致，当前 n_exp={kg_n_exp}，可尝试设置 KG_N_EXP"
                        )
        else:
            if verbose:
                print(f"⚠️  [KG] 未找到预训练模型: {model_path}")

        entity_short_set = {k.rstrip(">").rsplit("/", 1)[-1] for k in entity2id.keys()}
        kg_movie_resolution = build_kg_movie_resolution_index(movie_entities)
        if verbose:
            print(
                f"   对齐索引: lookup {len(kg_movie_resolution.get('lookup', {}))} 键, token {len(kg_movie_resolution.get('token_index', {}))} 词"
            )
        _cache.update(
            {
                "model": model,
                "model_args": (entity_num, relation_num, emb_dim, img_dim, text_dim),
                "entity2id": entity2id,
                "relation2id": relation2id,
                "id2entity": id2entity,
                "id2relation": id2relation,
                "entity_relations": entity_relations,
                "tail_relations": tail_relations,
                "movie_entities": movie_entities,
                "entity_short_set": entity_short_set,
                "kg_movie_resolution": kg_movie_resolution,
                "dataset": dataset,
                "train_adj_matrix": (adj_indices, adj_values),
            }
        )

        if verbose:
            print("📦 [KG] 正在构建索引...")

        elapsed = time.time() - start
        if verbose:
            print(
                f"✅ [KG] 加载完成：{len(movie_entities)} 部电影，耗时 {elapsed:.2f}s"
            )

        return True

    except Exception as e:
        return f"加载知识图谱失败: {str(e)}"


def _pick_moe_relations(
    relation2id: dict,
    user_input: str,
    genre_hints: Optional[list[str]],
    preferred: Optional[list[str]] = None,
    max_relations: int = 10,
) -> tuple[list[int], list[str]]:
    blob = (user_input or "") + " " + " ".join(genre_hints or [])
    blob_lc = blob.lower()

    chosen: list[str] = []

    def add_short(rs: str) -> None:
        if rs in chosen:
            return
        if _relation_short_to_id(rs, relation2id) is not None:
            chosen.append(rs)

    for rs in MOE_RELATION_CORE:
        add_short(rs)

    for rs in (preferred or []):
        if len(chosen) >= max_relations:
            break
        add_short(str(rs))

    keyword_rules = [
        (("续集", "下一部", "后续", "后传"), "subsequentWork"),
        (("前作", "前传", "上一部", "前集"), "previousWork"),
        (("改编", "原著", "基于"), "basedOn"),
        (("相关", "类似", "相近"), "related"),
        (("编剧", "剧本"), "writer"),
        (("制片", "出品"), "producer"),
        (("配乐", "作曲"), "musicComposer"),
        (("摄影", "镜头"), "cinematography"),
        (("剪辑",), "editing"),
        (("旁白", "解说"), "narrator"),
        (("国家", "地区"), "country"),
        (("语言", "对白"), "language"),
        (("奖", "奥斯卡", "戛纳"), "award"),
    ]
    ascii_kw = [
        (("sequel",), "subsequentWork"),
        (("prequel", "previous"), "previousWork"),
        (("based on", "adapted"), "basedOn"),
        (("related", "similar"), "related"),
        (("writer", "screenplay"), "writer"),
        (("producer",), "producer"),
        (("composer", "soundtrack"), "musicComposer"),
        (("cinematography", "cinematographer"), "cinematography"),
        (("editing", "editor"), "editing"),
        (("narrator",), "narrator"),
        (("country",), "country"),
        (("language",), "language"),
        (("award", "oscar"), "award"),
    ]

    for kws, rshort in keyword_rules:
        if any(kw in blob for kw in kws):
            add_short(rshort)
    for kws, rshort in ascii_kw:
        if any(kw in blob_lc for kw in kws):
            add_short(rshort)

    for rs in MOE_RELATION_FILL:
        if len(chosen) >= max_relations:
            break
        add_short(rs)

    chosen = chosen[:max_relations]

    rel_ids: list[int] = []
    rel_used: list[str] = []
    for rs in chosen:
        rid = _relation_short_to_id(rs, relation2id)
        if rid is not None:
            rel_ids.append(rid)
            rel_used.append(rs)
    return rel_ids, rel_used


def _short_name_to_entity_id(short: str, entity2id: dict) -> Optional[int]:
    for uri, eid in entity2id.items():
        if uri.rstrip(">").rsplit("/", 1)[-1] == short:
            return eid
    return None


def _relation_short_to_id(rel_short: str, relation2id: dict) -> Optional[int]:
    for uri, rid in relation2id.items():
        tail = uri.rstrip(">").rsplit("/", 1)[-1]
        if tail == rel_short:
            return rid
    return None


def _moe_genre_boost_applied(user_input: str, genre_hints: Optional[list[str]]) -> float:
    text = (user_input or "") + " " + " ".join(genre_hints or [])
    if any(g in text for g in ALLOWED_GENRES):
        return 1.25
    return 1.0


def moe_link_prediction_recommend(
    seed_shorts: list,
    topk: int = 8,
    user_input: str = "",
    genre_hints: Optional[list[str]] = None,
    preferred_relations: Optional[list[str]] = None,
    max_relations: int = 10,
    seed_weights: Optional[dict[str, float]] = None,
):
    empty_meta: dict = {
        "relations_used": [],
        "genre_boost": 1.0,
        "max_relations": max_relations,
    }

    # --- KG 结果缓存（种子+关系+类型不变时 1 小时内直接返回）---
    from backend.services.redis_cache import get as _kg_get, set as _kg_set
    _seed_sig = ",".join(sorted(seed_shorts or []))
    _rel_sig = ",".join(sorted(preferred_relations or []))
    _gh_sig = ",".join(sorted(genre_hints or []))
    _kg_raw = f"kg:{_seed_sig}:{_rel_sig}:{_gh_sig}:{topk}:{max_relations}"
    _kg_key = "kg_rec:" + hashlib.md5(_kg_raw.encode()).hexdigest()
    _kg_cached = _kg_get(_kg_key)
    if _kg_cached is not None:
        return _kg_cached.get("movies", []), _kg_cached.get("note", ""), _kg_cached.get("meta", empty_meta)

    model = _cache.get("model")
    train_adj = _cache.get("train_adj_matrix")
    entity2id = _cache.get("entity2id", {})
    id2entity = _cache.get("id2entity", {})
    movie_entities = _cache.get("movie_entities", set())
    relation2id = _cache.get("relation2id", {})
    rel_num = len(relation2id)

    if model is None:
        return [], "Multi_MoE 未加载，无法进行链路预测。", empty_meta
    if train_adj is None:
        return [], "缺少训练邻接矩阵，请确认 load_kg_model 已成功执行。", empty_meta

    seed_ids = []
    for s in seed_shorts or []:
        eid = _short_name_to_entity_id(s, entity2id)
        if eid is not None:
            seed_ids.append(eid)
    if not seed_ids:
        return (
            [],
            "种子无法映射到图谱实体 ID，请检查片名或 MOVIE_NAME_REVERSE_MAPPING。",
            empty_meta,
        )

    rel_ids, rel_used = _pick_moe_relations(
        relation2id,
        user_input,
        genre_hints,
        preferred=preferred_relations,
        max_relations=max_relations,
    )
    if not rel_ids:
        return [], "未在 relation2id 中解析到任何候选关系。", empty_meta

    genre_rid = _relation_short_to_id("genre", relation2id)
    gboost = _moe_genre_boost_applied(user_input, genre_hints)

    rid_to_short = {int(rid): rs for rid, rs in zip(rel_ids, rel_used)}

    def _hid_seed_weight(hid: int) -> float:
        if not seed_weights:
            return 1.0
        full = id2entity.get(hid, "")
        sh = full.rstrip(">").rsplit("/", 1)[-1] if full else ""
        try:
            return float(seed_weights.get(sh, 1.0))
        except (TypeError, ValueError):
            return 1.0

    def apply_score(eid: int, v: float, rid: int) -> float:
        rs = rid_to_short.get(int(rid), "")
        w = RELATION_WEIGHTS.get(rs, 1.0)
        out = v * float(w)
        if genre_rid is not None and int(rid) == int(genre_rid) and gboost != 1.0:
            out *= gboost
        return out

    entity_best = defaultdict(float)
    model.eval()

    def _env_int(name: str, default: int, *, min_v: int = 1, max_v: int = 50000) -> int:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            v = default
        else:
            try:
                v = int(raw)
            except ValueError:
                v = default
        return max(min_v, min(max_v, v))

    def _env_float(name: str, default: float, *, min_v: float = 0.0, max_v: float = 1000.0) -> float:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            v = default
        else:
            try:
                v = float(raw)
            except ValueError:
                v = default
        return max(min_v, min(max_v, v))

    # 加速：每个 (seed, relation, dir) 只保留 pred_avg 前 N 个候选。
    # 可设 KG_MOE_PER_QUERY_TOPN=0 恢复全量扫描。
    per_query_topn = _env_int("KG_MOE_PER_QUERY_TOPN", 1200, min_v=0, max_v=20000)
    with _model_inference_lock, torch.no_grad():
        for hid in seed_ids:
            for rid in rel_ids:
                batch_tail = torch.LongTensor([[hid, rid, hid]])
                try:
                    preds, _ = model.forward(batch_tail, train_adj)
                    # 四分支平均（与评估逻辑一致，pred_mm 单独性能接近零）
                    pred_avg = (preds[0][0] + preds[1][0] + preds[2][0] + preds[3][0]) / 4.0
                    hw = _hid_seed_weight(hid)
                    if per_query_topn and int(per_query_topn) > 0:
                        kq = min(int(pred_avg.shape[0]), int(per_query_topn))
                        vals, idxs = torch.topk(pred_avg, kq)
                        for v0, eid0 in zip(vals.tolist(), idxs.tolist()):
                            v = apply_score(int(eid0), float(v0), rid) * hw
                            if v > entity_best[int(eid0)]:
                                entity_best[int(eid0)] = v
                    else:
                        for eid in range(pred_avg.shape[0]):
                            v = apply_score(eid, float(pred_avg[eid].item()), rid) * hw
                            if v > entity_best[eid]:
                                entity_best[eid] = v
                except Exception as ex:
                    print(f"⚠️  [MoE-KG] tail forward 失败: {str(ex)[:80]}")

                inv_rid = int(rid) + rel_num
                if inv_rid < 2 * rel_num:
                    batch_head = torch.LongTensor([[hid, inv_rid, hid]])
                    try:
                        preds_h, _ = model.forward(batch_head, train_adj)
                        pred_avg_h = (preds_h[0][0] + preds_h[1][0] + preds_h[2][0] + preds_h[3][0]) / 4.0
                        hw = _hid_seed_weight(hid)
                        if per_query_topn and int(per_query_topn) > 0:
                            kq = min(int(pred_avg_h.shape[0]), int(per_query_topn))
                            vals, idxs = torch.topk(pred_avg_h, kq)
                            for v0, eid0 in zip(vals.tolist(), idxs.tolist()):
                                v = apply_score(int(eid0), float(v0), rid) * hw
                                if v > entity_best[int(eid0)]:
                                    entity_best[int(eid0)] = v
                        else:
                            for eid in range(pred_avg_h.shape[0]):
                                v = apply_score(eid, float(pred_avg_h[eid].item()), rid) * hw
                                if v > entity_best[eid]:
                                    entity_best[eid] = v
                    except Exception as ex:
                        print(f"⚠️  [MoE-KG] head-inv forward 失败: {str(ex)[:80]}")

    ranked_pairs = sorted(entity_best.items(), key=lambda x: -x[1])
    seed_short_set = set(seed_shorts or [])
    out = []

    # 保持原行为：确定性取 topK（KG 候选本身不做随机化；后续仍由“大模型定榜”筛选）
    for eid, _ in ranked_pairs:
        full = id2entity.get(eid, "")
        short = full.rstrip(">").rsplit("/", 1)[-1] if full else ""
        if short in movie_entities and short not in seed_short_set:
            out.append(short)
        if len(out) >= topk:
            break

    boost_note = f" genre 分数加权×{gboost}。" if gboost != 1.0 else ""
    w_note = "（已按关系权重加权）" if any(RELATION_WEIGHTS.get(r, 1.0) != 1.0 for r in rel_used) else ""
    note = (
        f"已调用 Multi_MoE.forward（四分支平均），对关系 {', '.join(rel_used)} 分别做了"
        f"「尾预测 (h,r,?)」与「头预测逆形式 (h,r+{rel_num},?)」双向打分并取 max 聚合。"
        f"{w_note}{boost_note} 种子数 {len(seed_ids)}，输出电影实体 {len(out)} 个。"
    )
    meta = {
        "relations_used": rel_used,
        "preferred_relations": list(preferred_relations or []),
        "relation_weights": {r: RELATION_WEIGHTS.get(r, 1.0) for r in rel_used},
        "genre_boost": gboost,
        "max_relations": max_relations,
        "seed_weights_applied": bool(seed_weights),
    }
    # 存入缓存（1 小时）
    try:
        _kg_set(_kg_key, {"movies": out, "note": note, "meta": meta}, ttl=3600)
    except Exception:
        pass
    return out, note, meta


def structural_bridge_seeds(
    seed_shorts: list,
    *,
    max_bridges: int = 4,
    per_seed: int = 12,
) -> list[str]:
    """
    从种子实体的 1 跳关系中取其它电影实体，作为单次 MoE 前的弱桥接种子（无额外 Multi_MoE.forward）。
    用于替代「首轮预测后再把预测当种子跑第二轮」的双次调用，与用户/RAG 对齐种子一并参与四分支平均预测。
    """
    er = _cache.get("entity_relations") or {}
    movie_entities = _cache.get("movie_entities") or set()
    seeds = set(seed_shorts or [])
    out: list[str] = []
    for s in seed_shorts or []:
        if len(out) >= max_bridges:
            break
        for _r, t in (er.get(s, []) or [])[:per_seed]:
            if len(out) >= max_bridges:
                break
            if t in movie_entities and t not in seeds and t not in out:
                out.append(t)
    return out


def intermediate_moe_seeds_from_movies(
    seed_shorts: list,
    *,
    max_seeds: int = 12,
    per_movie: int = 24,
    blocked: Optional[Set[str]] = None,
) -> Tuple[list[str], Dict[str, float]]:
    """
    多步语义（单次 forward 内）：从种子**电影**沿边（主演/导演/编剧等）得到非电影实体，
    按「被多少部种子电影共同连接」计数；高频者（如多部用户片同一演员）优先作为弱头实体，
    与电影种子一并输入 Multi_MoE，经 (h,r,?) / 逆关系预测指向其它电影。
    """
    er = _cache.get("entity_relations") or {}
    movie_entities = _cache.get("movie_entities") or set()
    entity2id = _cache.get("entity2id", {})
    short_set = _cache.get("entity_short_set")
    if short_set is None:
        short_set = {k.rstrip(">").rsplit("/", 1)[-1] for k in entity2id.keys()}
        _cache["entity_short_set"] = short_set

    blocked = blocked or set()
    rel_ok = MOE_INTERMEDIATE_FROM_MOVIE_RELATIONS
    # 中间实体 -> 连接到的种子电影集合（去重后计数 = 共现部数）
    co_movies: dict[str, set[str]] = defaultdict(set)

    for m in seed_shorts or []:
        if m not in movie_entities:
            continue
        for r, t in (er.get(m, []) or [])[:per_movie]:
            if not t or t in movie_entities or t in blocked:
                continue
            if r not in rel_ok:
                continue
            if t not in short_set:
                continue
            co_movies[t].add(m)

    scored = sorted(
        co_movies.items(),
        key=lambda kv: (-len(kv[1]), kv[0]),
    )
    out: list[str] = []
    weights: Dict[str, float] = {}
    base_w = 0.36
    for t, movies in scored[:max(1, max_seeds)]:
        freq = len(movies)
        w = min(0.58, base_w + 0.038 * max(0, freq - 1))
        out.append(t)
        weights[t] = w
    return out, weights


def _graph_expand_kg_neighbors(
    bridge_movies: list,
    seed_shorts: list,
    *,
    cap: int = 16,
    per_bridge: int = 10,
) -> list:
    """1-hop：从 MoE 召回电影经 entity_relations 扩展到其它电影实体（结构多跳、无额外 forward）。"""
    er = _cache.get("entity_relations") or {}
    movie_entities = _cache.get("movie_entities") or set()
    seeds = set(seed_shorts or [])
    out: list[str] = []
    for b in bridge_movies or []:
        if b not in movie_entities:
            continue
        for _r, t in (er.get(b, []) or [])[:per_bridge]:
            if t in movie_entities and t not in seeds and t not in out:
                out.append(t)
        if len(out) >= cap:
            break
    return out
