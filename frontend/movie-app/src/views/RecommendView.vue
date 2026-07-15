<template>
  <div
    class="recommend-page page-mesh"
    :class="{ 'recommend-page--static-bg': !dynamicPageBgEnabled }"
  >
    <div class="rec-hero-tools">
      <button
        type="button"
        class="rec-bg-mode-toggle"
        :aria-label="dynamicPageBgEnabled ? '切换为默认背景' : '切换为动态背景'"
        :title="dynamicPageBgEnabled ? '动态背景（开）— 点击改为默认底色' : '默认底色— 点击恢复动态背景'"
        @click="toggleDynamicBg"
      >
        <svg
          v-if="dynamicPageBgEnabled"
          class="rec-bg-mode-svg"
          viewBox="0 0 24 24"
          width="20"
          height="20"
          aria-hidden="true"
        >
          <path
            fill="currentColor"
            d="M4 6h2v12H4V6zm5 3h2v9H9V9zm5-5h2v14h-2V4zm5 4h2v10h-2V8z"
          />
        </svg>
        <svg v-else class="rec-bg-mode-svg" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path fill="currentColor" d="M4 5h16v14H4V5zm2 2v10h12V7H6z" />
        </svg>
      </button>
    </div>
    <header class="rec-hero">
      <div class="rec-hero-inner">
        <h1>智能推荐</h1>
        <p>
          结合你选择的类型、收藏、看过以及偏好描述，为你推荐电影。需要时可在页面下方生成解读或总结。
        </p>
      </div>
    </header>

    <el-card class="recommend-card glass" shadow="never">
      <template #header>
        <div class="rec-card-head">
          <div class="rec-card-head-text">
            <span class="rec-card-title">参数与偏好</span>
            <span class="rec-card-sub">选择类型与偏好，必要时勾选收藏；点击下方即可生成推荐。</span>
          </div>
        </div>
      </template>

      <el-form :model="form" class="rec-form" label-position="top">
        <section class="rec-panel">
          <header class="rec-panel-head">
            <span class="rec-panel-ico"><el-icon><Film /></el-icon></span>
            <div>
              <h3 class="rec-panel-title">类型倾向</h3>
              <p class="rec-panel-desc">可多选，与文字描述一起参与偏好建模</p>
            </div>
          </header>
          <el-checkbox-group v-model="form.selectedGenres" class="genre-wrap">
            <el-checkbox
              v-for="genre in availableGenres"
              :key="genre"
              :label="genre"
              :value="genre"
              class="rec-genre-chip"
            >
              {{ genre }}
            </el-checkbox>
          </el-checkbox-group>
        </section>

        <section class="rec-panel">
          <header class="rec-panel-head">
            <span class="rec-panel-ico"><el-icon><Star /></el-icon></span>
            <div>
              <h3 class="rec-panel-title">收藏列表</h3>
              <p class="rec-panel-desc">可选：勾选部分收藏协助推荐；不选则主要按类型与描述</p>
            </div>
          </header>
          <div class="favorites-selector">
            <div v-if="favorites.length === 0" class="empty-favorites">
              <el-empty description="暂无收藏，可先去片库收藏几部" :image-size="64" />
            </div>
            <el-checkbox-group v-else v-model="form.selectedFavorites" class="favorites-grid">
              <el-checkbox
                v-for="fav in favorites"
                :key="fav.movie_name"
                :label="fav.movie_name"
                :value="fav.movie_name"
                class="favorite-item"
              >
                <div class="favorite-info">
                  <span class="movie-name">{{ fav.movie_name.replace(/_/g, ' ') }}</span>
                  <span class="genres" v-if="fav.genres">{{ fav.genres }}</span>
                </div>
              </el-checkbox>
            </el-checkbox-group>
          </div>
        </section>

        <div class="rec-split">
          <section class="rec-panel rec-panel-grow">
            <header class="rec-panel-head">
              <span class="rec-panel-ico"><el-icon><EditPen /></el-icon></span>
              <div>
                <h3 class="rec-panel-title">偏好描述</h3>
                <p class="rec-panel-desc">补充导演、风格、想避开的类型等</p>
              </div>
            </header>
            <el-input
              v-model="form.userInput"
              type="textarea"
              :rows="4"
              placeholder="例如：喜欢诺兰式科幻，想轻松一点，不想看恐怖片…"
              maxlength="500"
              show-word-limit
              class="rec-textarea"
            />

            <div class="rec-recent-opt">
              <div class="rec-recent-left">
                <div class="rec-recent-title">追加最近上映</div>
                <div class="rec-recent-desc">
                  追加最近上映电影，优先根据喜好推荐；若都不匹配则推荐 1 部热度最高的新片
                </div>
              </div>
              <el-switch
                v-model="form.useRecent"
                size="large"
                inline-prompt
                active-text="开"
                inactive-text="关"
                class="rec-recent-switch"
              />
            </div>
          </section>
          <aside class="rec-panel rec-panel-aside">
            <header class="rec-panel-head compact">
              <span class="rec-panel-ico"><el-icon><MagicStick /></el-icon></span>
              <div>
                <h3 class="rec-panel-title">解读与总结</h3>
                <p class="rec-panel-desc">生成推荐后，在结果区点击按钮即可生成，不改变当前列表顺序</p>
              </div>
            </header>
            <p class="rec-switch-hint">解读与总结为可选，按需生成即可</p>
          </aside>
        </div>

        <section class="rec-panel">
          <header class="rec-panel-head">
            <span class="rec-panel-ico"><el-icon><Histogram /></el-icon></span>
            <div>
              <h3 class="rec-panel-title">定榜数量</h3>
              <p class="rec-panel-desc">决定最终展示数量：KG 名额 + 片库名额（TMDB 最近上映会额外追加 1—3 部）</p>
            </div>
          </header>
          <div class="rec-sliders">
            <div class="rec-slider-card">
              <div class="rec-slider-top">
                <span class="rec-slider-name">知识图谱</span>
                <span class="rec-slider-val">{{ form.topkKg }}</span>
              </div>
              <el-slider v-model="form.topkKg" :min="1" :max="10" :step="1" />
              <span class="rec-slider-range">1 — 10</span>
            </div>
            <div class="rec-slider-card">
              <div class="rec-slider-top">
                <span class="rec-slider-name">RAG</span>
                <span class="rec-slider-val">{{ form.topkRag }}</span>
              </div>
              <el-slider v-model="form.topkRag" :min="1" :max="10" :step="1" />
              <span class="rec-slider-range">1 — 10</span>
            </div>
          </div>
        </section>

        <div class="rec-actions">
          <div class="rec-cta-row">
            <el-button
              type="primary"
              size="large"
              round
              :loading="recommendStore.running"
              class="rec-cta"
              @click="onRecommend()"
            >
              开始推荐
            </el-button>
            <span v-if="recommendStore.running" class="rec-inline-progress">
              {{ recommendStore.progressText || '推荐中…' }}
              <span
                v-if="recommendStore.running && recommendStore.progressSteps.length > 0"
                class="rec-inline-progress-sub"
              >
                （第 {{ recommendStore.progressStep + 1 }} / {{ recommendStore.progressSteps.length }} 步）
              </span>
            </span>
          </div>
          <!-- 进度条 -->
          <el-progress
            v-if="recommendStore.running && recommendStore.progressSteps.length > 0"
            :percentage="Math.round(((recommendStore.progressStep + 1) / recommendStore.progressSteps.length) * 100)"
            :stroke-width="8"
            :show-text="false"
            class="rec-progress-bar"
          />
        </div>
      </el-form>

      <!-- 推荐错误持久展示 -->
      <el-alert
        v-if="recommendStore.error && !recommendStore.running"
        type="error"
        :closable="true"
        show-icon
        title="推荐失败"
        :description="recommendStore.error"
        class="rec-error-alert"
        @close="recommendStore.error = null"
      />

      <!-- 推荐结果 -->
      <div v-if="result" class="result-section">
        <el-divider content-position="left">推荐结果</el-divider>

        <div v-if="result.movies?.length" class="merged-block">
          <div class="merged-head">
            <h3>为您推荐</h3>
            <p class="merged-hint">以下为本次推荐结果，可直接浏览海报与简介，或加入片单。</p>
            <div v-if="userStore.userInfo" class="merged-tools">
              <el-select
                v-model="selectedPlaylistId"
                placeholder="选择片单"
                size="default"
                class="pl-select"
                :disabled="!playlists.length"
                clearable
              >
                <el-option v-for="p in playlists" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
              <span class="pl-hint">未选择片单时，将自动保存到默认片单</span>
              <el-button
                type="primary"
                :icon="CircleCheck"
                round
                :disabled="!(result.movies?.length)"
                @click="saveResultToPlaylist"
              >
                保存到片单
              </el-button>
              <el-button :icon="CopyDocument" round :disabled="!(result.movies?.length)" @click="generateShareListicle">
                生成分享
              </el-button>
            </div>
          </div>
          <div class="rec-card-strip rec-ntfx-strip">
            <article
              v-for="(m, idx) in sortedMovies"
              :key="m.name + idx"
              class="rec-ntfx-card"
            >
              <div class="rec-ntfx-stack">
                <img
                  v-if="cardPosterShow(m)"
                  class="rec-ntfx-cover"
                  :src="m.poster_url || ''"
                  alt=""
                  loading="lazy"
                  @error="cardPosterFail(m)"
                />
                <div v-else class="rec-ntfx-cover rec-ntfx-cover-ph" />
                <div class="rec-ntfx-blur-band" aria-hidden="true" />
                <div class="rec-ntfx-scrim" aria-hidden="true" />
                <span class="rec-ntfx-rank">{{ idx + 1 }}</span>
                <div class="rec-ntfx-content">
                  <h4 class="rec-ntfx-title">
                    {{ movieKey(m) }}
                    <span v-if="m.release_year" class="rec-ntfx-year">{{ m.release_year }}</span>
                  </h4>
                  <p class="rec-ntfx-meta-line">
                    <span class="rec-ntfx-lbl">类型</span>{{ cardGenres(m) }}
                  </p>
                  <p class="rec-ntfx-meta-line">
                    <span class="rec-ntfx-lbl">评分</span>{{ cardScore(m) }}
                  </p>
                  <p class="rec-ntfx-blurb">{{ cardShortReview(m) }}</p>
                </div>
              </div>
            </article>
          </div>
        </div>
        <el-empty v-else description="本次未生成推荐，可先收藏或浏览几部影片后再试" />

        <div v-if="result.llm_summary" class="llm-summary-section">
          <h3>推荐总结</h3>
          <el-card shadow="never" class="llm-summary-card">
            <div class="llm-summary-text">{{ result.llm_summary }}</div>
          </el-card>
        </div>
        <div class="llm-summary-actions">
          <el-button
            type="primary"
            round
            :loading="recommendStore.explainRunning"
            :disabled="recommendStore.running"
            @click="onGenerateExplain"
          >
            生成解读
          </el-button>
          <el-button
            type="primary"
            round
            :loading="recommendStore.summaryRunning"
            :disabled="recommendStore.running"
            @click="onGenerateSummary"
          >
            生成推荐总结
          </el-button>
          <span class="llm-summary-hint">推荐生成完成后即可点击，按需查看解读或整段总结。</span>
        </div>

        <section
          v-if="!userStore.isAdmin && recommendSnapshotPayload"
          class="rec-snapshot-embed-wrap"
        >
          <h3 class="rec-snapshot-embed-h">推荐快照</h3>
          <RecommendSnapshotBody :payload="recommendSnapshotPayload" embedded />
        </section>

        <el-alert
          v-if="!result.llm_summary && result.llm_summary_error"
          type="info"
          :closable="false"
          show-icon
          title="总结未生成"
          :description="result.llm_summary_error"
          class="llm-error-alert"
        />

        <div v-if="result.llm_explanation" class="llm-explain-section user-llm">
          <h3>推荐解读</h3>
          <el-card shadow="never" class="llm-explain-card">
            <div class="llm-explain-text">{{ result.llm_explanation }}</div>
          </el-card>
        </div>
        <el-alert
          v-else-if="result.llm_explanation_error"
          type="warning"
          :closable="false"
          show-icon
          title="解读未生成"
          :description="result.llm_explanation_error"
          class="llm-error-alert"
        />

        <section v-if="userStore.isAdmin && result.pipeline?.length" class="admin-insight">
          <div class="admin-insight-head">
            <el-icon class="admin-insight-icon"><Cpu /></el-icon>
            <div>
              <h3 class="admin-insight-title">管理员 · 推理过程</h3>
              <p class="admin-insight-sub">
                主链路说明、偏好分解摘要、逐步调用链与图谱 MoE 元信息（仅管理员可见）
              </p>
            </div>
          </div>

          <el-collapse v-model="adminCollapse" class="admin-collapse glass-inner">
            <el-collapse-item name="pipeline">
              <template #title>
                <span class="collapse-title-row">
                  <el-icon><Share /></el-icon>
                  模型调用过程
                  <el-tag size="small" effect="plain" round class="collapse-count">{{
                    result.pipeline?.length ?? 0
                  }}</el-tag>
                </span>
              </template>
              <div v-if="result.kg_model_meta?.flow_summary" class="kg-note admin-pipeline-preamble">
                <span class="kg-label">主链路说明</span>
                <p>{{ result.kg_model_meta.flow_summary }}</p>
              </div>
              <div v-if="result.preference_decompose && prefDecomposeHasAny" class="kg-note admin-pref-decompose">
                <span class="kg-label">偏好分解（LLM 摘要）</span>
                <p v-if="result.preference_decompose.query" class="admin-pref-line">
                  <span class="admin-pref-k">RAG 查询增强</span>
                  {{ result.preference_decompose.query }}
                </p>
                <div
                  v-if="(result.preference_decompose.liked_genres || []).length"
                  class="admin-pref-line admin-pref-chips"
                >
                  <span class="admin-pref-k">偏好类型</span>
                  <div class="admin-pref-chip-list">
                    <el-tag
                      v-for="g in result.preference_decompose.liked_genres"
                      :key="'g-' + g"
                      size="small"
                      effect="plain"
                      round
                      >{{ g }}</el-tag
                    >
                  </div>
                </div>
                <div
                  v-if="(result.preference_decompose.relations || []).length"
                  class="admin-pref-line admin-pref-chips"
                >
                  <span class="admin-pref-k">关系线索</span>
                  <div class="admin-pref-chip-list">
                    <el-tag
                      v-for="r in result.preference_decompose.relations"
                      :key="'r-' + r"
                      size="small"
                      type="info"
                      effect="dark"
                      round
                      >{{ r }}</el-tag
                    >
                  </div>
                </div>
                <p
                  v-if="(result.preference_decompose.constraints || []).length"
                  class="admin-pref-line"
                >
                  <span class="admin-pref-k">约束要点</span>
                  {{ (result.preference_decompose.constraints || []).join('；') }}
                </p>
                <div
                  v-if="(result.preference_decompose.must_have_constraints || []).length"
                  class="admin-pref-line admin-pref-chips"
                >
                  <span class="admin-pref-k">硬约束</span>
                  <div class="admin-pref-chip-list">
                    <el-tag
                      v-for="c in result.preference_decompose.must_have_constraints"
                      :key="'mh-' + c"
                      size="small"
                      type="danger"
                      effect="plain"
                      round
                      >{{ c }}</el-tag
                    >
                  </div>
                </div>
                <div
                  v-if="(result.preference_decompose.soft_constraints || []).length"
                  class="admin-pref-line admin-pref-chips"
                >
                  <span class="admin-pref-k">软偏好</span>
                  <div class="admin-pref-chip-list">
                    <el-tag
                      v-for="c in result.preference_decompose.soft_constraints"
                      :key="'sf-' + c"
                      size="small"
                      type="warning"
                      effect="plain"
                      round
                      >{{ c }}</el-tag
                    >
                  </div>
                </div>
              </div>
              <div class="pipeline-track">
                <div
                  v-for="(step, idx) in result.pipeline"
                  :key="`${step.id}-${idx}`"
                  class="pipe-step"
                  :data-status="step.status"
                >
                  <div class="pipe-rail">
                    <span v-if="idx > 0" class="pipe-line pipe-line-before" />
                    <span class="pipe-dot" :class="'st-' + (step.status || 'info')">
                      <el-icon v-if="step.status === 'ok'"><CircleCheck /></el-icon>
                      <el-icon v-else-if="step.status === 'warn'"><WarningFilled /></el-icon>
                      <el-icon v-else-if="step.status === 'error'"><CircleClose /></el-icon>
                      <el-icon v-else><Timer /></el-icon>
                    </span>
                    <span
                      v-if="idx < (result.pipeline?.length ?? 0) - 1"
                      class="pipe-line pipe-line-after"
                    />
                  </div>
                  <div class="pipe-card">
                    <div class="pipe-card-top">
                      <div class="pipe-card-top-main">
                        <span class="pipe-step-title">{{ step.title }}</span>
                        <el-tag
                          v-if="step.call_kind === 'llm'"
                          size="small"
                          type="danger"
                          effect="plain"
                          round
                          class="pipe-llm-tag"
                          >LLM</el-tag
                        >
                      </div>
                      <span v-if="step.elapsed_ms != null && step.elapsed_ms > 0" class="pipe-ms">{{ step.elapsed_ms }} ms</span>
                    </div>
                    <p class="pipe-step-msg">
                      <span>{{ step.message }}</span>
                      <span class="pipe-step-id">{{ step.id }}</span>
                    </p>
                    <!-- 不展示模型名（避免与部署环境不一致造成误解） -->
                  </div>
                </div>
              </div>
            </el-collapse-item>

            <el-collapse-item name="kgmeta">
              <template #title>
                <span class="collapse-title-row">
                  <el-icon><Connection /></el-icon>
                  图谱元信息与候选
                </span>
              </template>
              <div v-if="result.kg_model_meta" class="kg-panel">
                <div class="kg-method-block">
                  <span class="kg-label">推理路径</span>
                  <p class="kg-method">{{ result.kg_model_meta.method }}</p>
                </div>
                <div class="kg-stat-row">
                  <div class="kg-stat">
                    <span class="kg-stat-k">genre 加权</span>
                    <span class="kg-stat-v">×{{ Number(result.kg_model_meta.genre_boost ?? 1).toFixed(2) }}</span>
                  </div>
                  <div class="kg-stat">
                    <span class="kg-stat-k">关系上限</span>
                    <span class="kg-stat-v">{{ result.kg_model_meta.max_relations ?? '—' }}</span>
                  </div>
                  <div class="kg-stat wide">
                    <span class="kg-stat-k">总耗时</span>
                    <span class="kg-stat-v">{{ result.elapsed_ms }} ms</span>
                  </div>
                </div>
                <div v-if="(result.kg_model_meta.relations_used || []).length" class="kg-chip-block">
                  <span class="kg-label">本次使用关系</span>
                  <div class="kg-chips">
                    <el-tag
                      v-for="r in result.kg_model_meta.relations_used"
                      :key="r"
                      size="small"
                      effect="plain"
                      class="kg-chip"
                      >{{ r }}</el-tag
                    >
                  </div>
                </div>
                <div
                  v-if="(result.kg_model_meta.preferred_relations || []).length"
                  class="kg-chip-block"
                >
                  <span class="kg-label">偏好关系（LLM / 约束）</span>
                  <div class="kg-chips">
                    <el-tag
                      v-for="r in result.kg_model_meta.preferred_relations"
                      :key="'p-' + r"
                      size="small"
                      type="info"
                      effect="dark"
                      class="kg-chip pref"
                      >{{ r }}</el-tag
                    >
                  </div>
                </div>
                <div v-if="relationWeightEntries.length" class="kg-weight-grid">
                  <span class="kg-label">关系权重（规则层）</span>
                  <div class="kg-weights">
                    <div v-for="[rel, w] in relationWeightEntries" :key="rel" class="kg-weight-row">
                      <span class="kg-w-name">{{ rel }}</span>
                      <div class="kg-w-bar-wrap">
                        <div class="kg-w-bar" :style="{ width: relationWeightPct(w) + '%' }" />
                      </div>
                      <span class="kg-w-num">{{ Number(w).toFixed(2) }}</span>
                    </div>
                  </div>
                </div>
                <div v-if="result.kg_model_meta.note" class="kg-note">
                  <span class="kg-label">模型说明</span>
                  <p>{{ result.kg_model_meta.note }}</p>
                </div>
                <div v-if="result.kg_model_meta.candidate_stage" class="kg-note kg-stage-note">
                  <span class="kg-label">候选阶段</span>
                  <p>{{ result.kg_model_meta.candidate_stage }}</p>
                  <p class="kg-stage-sub">
                    图谱一路为 MoE 链路预测；片库 RAG、豆瓣等与「同偏好他人收藏」并入后经大模型审核定榜，再统一补全海报与卡片字段。解读/总结为按需 LLM。
                  </p>
                </div>
              </div>
              <el-row :gutter="16" class="raw-lists-row raw-lists-row--triple">
                <el-col :xs="24" :md="8">
                  <div class="raw-list-card">
                    <div class="raw-list-head">
                      <span>图谱侧原始列表（MoE 召回）</span>
                      <el-tag size="small" round effect="plain">{{ result.kg_movies?.length ?? 0 }}</el-tag>
                    </div>
                    <p class="raw-list-legend">
                      <span class="lg-final">■</span> 定榜保留（进入最终推荐）
                      <span class="lg-pool">■</span> 仅候选池
                    </p>
                    <ol v-if="result.kg_movies?.length" class="raw-list raw-list-kg">
                      <li
                        v-for="(item, idx) in result.kg_movies"
                        :key="idx"
                        :class="kgFinalEntitySet.has(item) ? 'kg-raw-final' : 'kg-raw-pool'"
                      >
                        {{ item.replace(/_/g, ' ') }}
                      </li>
                    </ol>
                    <div v-else class="raw-empty">无输出</div>
                  </div>
                </el-col>
                <el-col :xs="24" :md="8">
                  <div class="raw-list-card rag">
                    <div class="raw-list-head">
                      <span>片库检索候选（RAG / 豆瓣）</span>
                      <el-tag size="small" round effect="plain">{{ result.rag_movies?.length ?? 0 }}</el-tag>
                    </div>
                    <ol v-if="result.rag_movies?.length" class="raw-list">
                      <li
                        v-for="(item, idx) in result.rag_movies"
                        :key="idx"
                        :class="finalTitleSet.has(_normTitle(item.name)) ? 'rag-raw-final' : 'rag-raw-pool'"
                      >
                        {{ item.name }}
                        <span v-if="item.similarity != null" class="raw-sim"
                          >{{ (item.similarity * 100).toFixed(1) }}%</span
                        >
                      </li>
                    </ol>
                    <div v-else class="raw-empty">无输出</div>
                  </div>
                </el-col>
                <el-col :xs="24" :md="8">
                  <div class="raw-list-card rag peer-fav-card">
                    <div class="raw-list-head">
                      <span>同偏好 · 他人收藏候选</span>
                      <el-tag size="small" round effect="plain">{{ result.peer_fav_movies?.length ?? 0 }}</el-tag>
                    </div>
                    <p class="raw-list-legend">
                      <span class="lg-final">■</span> 定榜保留（进入最终推荐）
                      <span class="lg-pool">■</span> 仅候选池
                    </p>
                    <ol v-if="result.peer_fav_movies?.length" class="raw-list">
                      <li
                        v-for="(item, idx) in result.peer_fav_movies"
                        :key="idx"
                        :class="finalTitleSet.has(_normTitle(item.name)) ? 'rag-raw-final' : 'rag-raw-pool'"
                      >
                        {{ item.display || item.name }}
                        <span v-if="item.weight != null" class="raw-sim peer-w">{{ Number(item.weight).toFixed(2) }}</span>
                      </li>
                    </ol>
                    <div v-else class="raw-empty">无输出</div>
                  </div>
                </el-col>
              </el-row>
            </el-collapse-item>

            <el-collapse-item v-if="result.recommend_text" name="rules">
              <template #title>
                <span class="collapse-title-row">
                  <el-icon><Document /></el-icon>
                  规则生成文本
                </span>
              </template>
              <div class="rule-text-panel">
                <div class="rule-text-toolbar">
                  <span class="rule-hint"
                    >定榜后的规则层清单（合并 KG/RAG、排除已看与负反馈、加权与审核后的输出，供审计与复制）</span
                  >
                  <el-button size="small" round type="primary" plain @click.stop="copyRecommendText">
                    <el-icon class="btn-ic"><CopyDocument /></el-icon>
                    复制全文
                  </el-button>
                </div>
                <pre class="rule-text-body">{{ result.recommend_text }}</pre>
              </div>
            </el-collapse-item>
          </el-collapse>
        </section>
      </div>

      <!-- 分享：杂志清单体 HTML，可下载 -->
      <el-dialog
        v-model="shareVisible"
        :show-close="false"
        width="820px"
        destroy-on-close
        class="share-listicle-dialog"
        :append-to-body="true"
        top="4vh"
        @closed="onShareDialogClosed"
      >
        <template #header>
          <div class="share-listicle-head">
            <span class="share-listicle-head-title">分享预览</span>
            <button
              type="button"
              class="share-listicle-head-close"
              aria-label="关闭"
              @click="shareVisible = false"
            >
              <el-icon><CircleClose /></el-icon>
            </button>
          </div>
        </template>
        <div class="dlg">
          <iframe v-if="shareFullDoc" class="share-listicle-iframe" title="分享预览" :srcdoc="shareFullDoc" />
          <el-empty v-else description="请先在上方点击「生成分享」" />
        </div>
        <template #footer>
          <div class="share-listicle-footer">
            <el-button type="primary" round class="dlg-save" :disabled="!shareFullDoc" @click="downloadShareHtml">
              保存
            </el-button>
          </div>
        </template>
      </el-dialog>
     </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useDynamicPageBackground } from '@/composables/useDynamicPageBackground'
import { useUserStore } from '@/stores/user'
import { useRecommendStore } from '@/stores/recommend'
import { movieApi, userApi } from '@/services/api'
import { ElMessage } from 'element-plus'
import {
  Cpu,
  Share,
  Connection,
  Document,
  CopyDocument,
  CircleCheck,
  WarningFilled,
  CircleClose,
  Timer,
  Film,
  Star,
  EditPen,
  MagicStick,
  Histogram
} from '@element-plus/icons-vue'
import type { RecommendResult, Favorite } from '@/types'
import { plainReviewText } from '@/utils/plainReview'
import RecommendSnapshotBody from '@/components/RecommendSnapshotBody.vue'
import type { RecommendSnapshotPayload } from '@/components/RecommendSnapshotBody.vue'

const userStore = useUserStore()
const recommendStore = useRecommendStore()
const { dynamicPageBgEnabled, toggleDynamicBg } = useDynamicPageBackground()

// 固定的10种电影类型
const ALLOWED_GENRES = [
  '剧情',
  '喜剧',
  '爱情',
  '动作',
  '科幻',
  '悬疑',
  '动画',
  '纪录片',
  '战争',
  '奇幻'
]

/** 与路由无关：存于 pinia，切页后再回来勾选仍在 */
const form = recommendStore.formPrefs

// recommending / progress：主链路用 running；短评二阶段用 blurbsRunning（切页不丢）
const result = ref<RecommendResult | null>(recommendStore.last)
watch(
  () => recommendStore.last,
  (v) => {
    result.value = v
  }
)
const favorites = ref<Favorite[]>([])
const availableGenres = ref<string[]>(ALLOWED_GENRES)

type PlaylistRow = { id: number; name: string; description: string }
const playlists = ref<PlaylistRow[]>([])
const selectedPlaylistId = ref<number | null>(null)
/** 管理员技术区默认展开「调用过程」与「图谱元信息」 */
const adminCollapse = ref(['pipeline', 'kgmeta'])

const kgFinalEntitySet = computed(() => {
  const names = result.value?.kg_final_entity_names
  if (!names?.length) return new Set<string>()
  return new Set(names.map((x) => String(x)))
})

const _normTitle = (s: string) =>
  String(s || '')
    .trim()
    .toLowerCase()
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')

const finalTitleSet = computed(() => {
  const ms = (result.value?.movies || []) as any[]
  const out = new Set<string>()
  for (const m of ms) {
    const t = _normTitle(String(m?.display || m?.name || ''))
    if (t) out.add(t)
  }
  return out
})

const prefDecomposeHasAny = computed(() => {
  const p = result.value?.preference_decompose
  if (!p) return false
  return Boolean(
    (p.query && p.query.trim()) ||
      (p.liked_genres && p.liked_genres.length) ||
      (p.relations && p.relations.length) ||
      (p.constraints && p.constraints.length) ||
      (p.must_have_constraints && p.must_have_constraints.length) ||
      (p.soft_constraints && p.soft_constraints.length) ||
      (p.movie_entities_zh && p.movie_entities_zh.length) ||
      (p.movie_entity_candidates_en && Object.keys(p.movie_entity_candidates_en).length)
  )
})

const relationWeightEntries = computed(() => {
  const rw = result.value?.kg_model_meta?.relation_weights
  if (!rw || typeof rw !== 'object') return [] as [string, number][]
  return Object.entries(rw)
    .map(([k, v]) => [k, Number(v)] as [string, number])
    .filter(([, v]) => !Number.isNaN(v))
    .sort((a, b) => b[1] - a[1])
})

const maxRelationWeight = computed(() => {
  const es = relationWeightEntries.value
  if (!es.length) return 1
  return Math.max(...es.map(([, w]) => w), 0.001)
})

function relationWeightPct(w: number) {
  return Math.min(100, (w / maxRelationWeight.value) * 100)
}

async function copyRecommendText() {
  const t = result.value?.recommend_text
  if (!t) return
  try {
    await navigator.clipboard.writeText(t)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

// 推荐结果不提供“点击看详情”，详情请去片单页查看

const loadPlaylists = async () => {
  if (!userStore.userInfo) return
  try {
    const pl = await userApi.getPlaylists()
    if (pl.data?.success) playlists.value = pl.data.playlists || []
  } catch {
    /* ignore */
  }
}

const movieKey = (m: any) => (m?.display || m?.name || '').toString().trim()

const sortedMovies = computed(() => {
  const ms = (result.value?.movies || []) as any[]
  if (!ms.length) return []
  // 保持后端定榜顺序：后端已完成合并加权、审核与定榜；这里不再按来源重排。
  return [...ms]
})

const saveResultToPlaylist = async () => {
  if (!result.value?.movies?.length) return
  try {
    const movies = sortedMovies.value.map((m: any) => ({
      name: movieKey(m),
      source: m.source || '',
      tmdb_id: m.tmdb_id ?? null,
      genres: '',
      poster_url: m.poster_url || '',
      genres_str: m.genres_str || '',
      score_str: m.score_str || '',
      short_review: m.short_review || ''
    }))
    let targetId = selectedPlaylistId.value
    let targetName = ''
    if (!targetId) {
      const now = new Date()
      const pad = (n: number) => String(n).padStart(2, '0')
      const base = '智能推荐电影'
      const exists = (playlists.value || []).some((p) => (p?.name || '').toString().trim() === base)
      const name = exists ? `${base} ${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}` : base
      const created = await userApi.createPlaylist(name, '由智能推荐自动创建')
      targetId = Number(created.data?.id || created.data?.playlist?.id || 0)
      targetName = name
      if (!targetId) throw new Error('创建片单失败')
      selectedPlaylistId.value = targetId
      await loadPlaylists()
    } else {
      const p = (playlists.value || []).find((x) => Number(x.id) === Number(targetId))
      targetName = p?.name || ''
    }

    const res = await userApi.saveRecommendationToPlaylist(targetId, movies)
    if (res.data?.success) {
      ElMessage.success(`已保存到片单：${targetName || targetId}（新增 ${res.data.added ?? 0} 条）`)
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

const shareVisible = ref(false)
const shareFullDoc = ref('')
const cardPosterBroken = ref<Record<string, boolean>>({})

const onShareDialogClosed = () => {
  shareFullDoc.value = ''
}

function escapeHtml(s: string): string {
  if (s == null || s === undefined) return ''
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function cardGenres(m: any): string {
  const g = m?.genres_str
  if (g && String(g).trim()) return String(g).trim()
  const raw = m?.genres
  if (Array.isArray(raw)) return raw.filter(Boolean).join('、')
  if (typeof raw === 'string' && raw.trim()) return raw.trim()
  return '—'
}

function cardScore(m: any): string {
  const s = m?.score_str ?? m?.score
  if (s !== undefined && s !== null && String(s).trim() !== '') return String(s).trim()
  return '—'
}

function cardShortReview(m: any): string {
  const t = plainReviewText(m?.short_review)
  if (t) return t
  // 两阶段推荐：短评可能稍后异步回填；未生成时保持空白即可
  return ''
}

function cardPosterShow(m: any): boolean {
  const k = movieKey(m)
  if (cardPosterBroken.value[k]) return false
  return !!(m?.poster_url && String(m.poster_url).trim())
}

function cardPosterFail(m: any) {
  const k = movieKey(m)
  if (k) cardPosterBroken.value = { ...cardPosterBroken.value, [k]: true }
}

function smallListicleSummary(ms: any[]): string {
  const titles = ms.map((m) => movieKey(m)).filter(Boolean)
  const top3 = titles.slice(0, 3)
  const allGenres = new Map<string, number>()
  for (const m of ms) {
    const g = String(cardGenres(m) || '').trim()
    if (!g || g === '—') continue
    for (const part of g.replace('、', '/').split('/')) {
      const p = part.trim()
      if (!p) continue
      allGenres.set(p, (allGenres.get(p) || 0) + 1)
    }
  }
  const hotGenres = [...allGenres.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([g]) => g)
  const gtxt = hotGenres.length ? `类型上以「${hotGenres.join(' / ')}」为主` : '覆盖多种题材'
  const picks = top3.length ? `优先推荐：${top3.join('、')}。` : ''
  return `为你挑选了 ${ms.length} 部影片，${gtxt}；每部都附上关键信息与推荐理由，方便快速挑片。${picks}`.trim()
}

/** 分享清单里「主演」只展示前几位，避免一行过长 */
function formatShareCast(raw: string, maxNames = 5): string {
  let s = (raw || '').toString().trim()
  if (!s) return ''
  // 后端有时是 Python 列表字面量：['a'、'b']，去掉 [] 与单/弯引号再按顿号拆分
  s = s.replace(/[\[\]]/g, '')
  s = s.replace(/['\u2018\u2019\u201c\u201d]/g, '')
  const parts = s
    .split(/[,，、/|]/)
    .map((x) => x.trim())
    .filter(Boolean)
  return parts.slice(0, maxNames).join('、')
}

async function fetchAsDataUrl(url: string): Promise<string> {
  const u = (url || '').toString().trim()
  if (!u) return ''
  if (u.startsWith('data:')) return u
  try {
    const res = await fetch(u, { mode: 'cors' as any, credentials: 'omit' as any })
    if (!res.ok) return ''
    const blob = await res.blob()
    if (!blob || blob.size < 32) return ''
    if (!String(blob.type || '').startsWith('image/')) return ''
    return await new Promise<string>((resolve) => {
      const fr = new FileReader()
      fr.onload = () => resolve(String(fr.result || ''))
      fr.onerror = () => resolve('')
      fr.readAsDataURL(blob)
    })
  } catch {
    return ''
  }
}

async function fetchMovieDetailForShare(m: any): Promise<any> {
  const name = movieKey(m)
  const src = String(m?.source || '').trim()
  const tid = m?.tmdb_id != null ? Number(m.tmdb_id) : undefined
  try {
    const res = await movieApi.getMovieDetailNoTrack(name, src || undefined, tid)
    return res.data?.data || res.data?.movie || res.data || {}
  } catch {
    return {}
  }
}

async function buildListicleShareDocument(): Promise<string> {
  const ms = sortedMovies.value || []
  const dateStr = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
  const lead = smallListicleSummary(ms)
  const css = `
    body { margin:0; background:#faf7f2; color:#1a1a1a; font-family: Georgia, "Times New Roman", "Noto Serif SC", serif; }
    .wrap { max-width: 820px; margin: 0 auto; padding: 40px 28px 56px; }
    .site-hd h1 { font-size: 2.05rem; font-weight: 800; margin: 0 0 12px; line-height: 1.15; letter-spacing: -0.02em; }
    .deck { font-size: 1rem; color:#444; margin:0 0 8px; font-family: ui-sans-serif,system-ui,sans-serif; }
    .subdeck { font-size: 0.98rem; color:#555; line-height:1.65; margin:0 0 30px; font-family: ui-sans-serif,system-ui,sans-serif; }
    .sl-item { border-top: 1px solid #e2ddd4; padding: 28px 0 32px; position: relative; }
    .sl-item:first-of-type { border-top: none; }
    .sl-num { position:absolute; left:0; top:30px; width:40px; height:40px; border-radius:10px; background:#111; color:#fff; font: 800 18px/40px ui-sans-serif,system-ui,sans-serif; text-align:center; }
    .sl-row { display:flex; gap:18px; margin-left:56px; align-items:flex-start; }
    .sl-row.alt { flex-direction: row-reverse; }
    .sl-poster { width: 160px; flex: 0 0 160px; }
    .sl-poster img { width: 160px; height: 240px; object-fit: cover; border-radius: 14px; display:block; box-shadow: 0 18px 40px rgba(0,0,0,0.16); }
    .sl-poster .ph { width: 160px; height: 240px; border-radius: 14px; background: linear-gradient(135deg,#ddd,#f6f6f6); border: 1px solid #e6e0d6; }
    .sl-body { flex: 1; min-width: 0; }
    .sl-title { font-size: 1.55rem; font-weight: 800; margin: 0 0 12px; line-height:1.2; }
    .sl-meta { font: 650 14px/1.55 ui-sans-serif,system-ui,sans-serif; color:#444; margin:0 0 10px; }
    .sl-meta span { display:inline-block; margin-right: 14px; }
    .sl-meta b { color:#111; font-weight: 800; }
    .sl-reason { font: 650 15px/1.7 ui-sans-serif,system-ui,sans-serif; color:#222; margin: 0 0 10px; }
    .sl-text { font-size:1.02rem; line-height:1.75; color:#333; margin:0; }
    .lead { margin: 12px 0 0; padding: 12px 14px; border-radius: 14px; background: #fff; border: 1px solid #eee5da; color:#333; font: 500 0.98rem/1.65 ui-sans-serif,system-ui,sans-serif; }
    @media (max-width: 720px) {
      .wrap { padding: 28px 18px 46px; }
      .sl-row, .sl-row.alt { flex-direction: column; margin-left: 0; }
      .sl-num { position: static; margin: 0 0 10px; }
      .sl-poster, .sl-poster img, .sl-poster .ph { width: 100%; height: auto; }
      .sl-poster img { aspect-ratio: 2 / 3; }
    }
  `
  const details = await Promise.all(ms.map((m) => fetchMovieDetailForShare(m)))

  const toAbs = (u: string) => {
    const s = (u || '').toString().trim()
    if (!s) return ''
    if (s.startsWith('data:')) return s
    if (s.startsWith('http://') || s.startsWith('https://')) return s
    if (s.startsWith('/')) return `${window.location.origin}${s}`
    return s
  }

  const posterCandidates = ms.map((m, i) => {
    const d = details[i] || {}
    return (
      String(m?.poster_url || '').trim() ||
      String(d?.poster_url || d?.poster || '').trim()
    )
  })

  const posters = await Promise.all(posterCandidates.map((u) => fetchAsDataUrl(toAbs(u))))

  const items = ms
    .map((m, i) => {
      const d = details[i] || {}
      const title = escapeHtml(movieKey(m))
      const genres = escapeHtml(cardGenres(m))
      const score = escapeHtml(cardScore(m))
      const cast = escapeHtml(formatShareCast(String(d.actor || d.cast || '').toString().trim()))
      const startTime = escapeHtml(String(d.start_time || d.release_date || '').toString().trim())
      const overview = escapeHtml(String(d.overview || '').toString().trim())

      const reasonRaw = plainReviewText(m?.short_review) || plainReviewText(d?.short_review) || ''
      const reason = escapeHtml(String(reasonRaw || '').toString().trim())

      // 优先使用 base64（离线可用）；若拉取失败则用绝对 URL（在线可用，避免 file:// 下相对路径裂图）
      const posterData = (posters[i] || '').toString().trim()
      const posterFallback = toAbs(String(posterCandidates[i] || '').trim())
      const poster = posterData || posterFallback
      const posterHtml = poster ? `<img src="${escapeHtml(poster)}" alt="" />` : `<div class="ph"></div>`
      const alt = i % 2 === 1 ? ' alt' : ''

      const metaParts: string[] = []
      metaParts.push(`<span><b>类型</b> ${genres || '—'}</span>`)
      metaParts.push(`<span><b>评分</b> ${score || '—'}</span>`)
      if (startTime) metaParts.push(`<span><b>上映</b> ${startTime}</span>`)
      if (cast) metaParts.push(`<span><b>主演</b> ${cast}</span>`)
      const meta = metaParts.join('')

      const reasonHtml = reason ? `<p class="sl-reason">${reason}</p>` : ''
      const overviewHtml = overview ? `<p class="sl-text">${overview}</p>` : ''
      return `<article class="sl-item"><div class="sl-num">${i + 1}</div><div class="sl-row${alt}"><div class="sl-poster">${posterHtml}</div><div class="sl-body"><h2 class="sl-title">${title}</h2><p class="sl-meta">${meta}</p>${reasonHtml}${overviewHtml}</div></div></article>`
    })
    .join('')

  const leadHtml = lead ? `<p class="subdeck">${escapeHtml(lead)}</p>` : ''
  return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>MovieHub·影片推荐</title><style>${css}</style></head><body><div class="wrap"><header class="site-hd"><h1>MovieHub·影片推荐</h1><p class="deck">${escapeHtml(
    dateStr
  )}</p>${leadHtml}</header><main>${items}</main></div></body></html>`
}

const generateShareListicle = async () => {
  if (!result.value?.movies?.length) {
    ElMessage.warning('暂无推荐结果')
    return
  }
  shareVisible.value = true
  shareFullDoc.value = ''
  try {
    shareFullDoc.value = await buildListicleShareDocument()
  } catch {
    shareFullDoc.value = ''
    ElMessage.error('生成分享失败')
  }
}

const downloadShareHtml = () => {
  if (!shareFullDoc.value) return
  const blob = new Blob([shareFullDoc.value], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `movie_recommend_share_${Date.now()}.html`
  a.click()
  URL.revokeObjectURL(url)
}

// 加载收藏
const loadData = async () => {
  try {
    if (userStore.userInfo) {
      const favResponse = await userApi.getMyFavorites()
      favorites.value = favResponse.data.favorites || []
      try {
        const pr = await userApi.getUserProfile()
        const prefs = pr.data?.user?.preferred_genres as string[] | undefined
        /* 仅当用户尚未勾选任何类型时，用资料里的偏好类型打底，避免覆盖已保存的勾选 */
        if (prefs?.length && form.selectedGenres.length === 0) {
          for (const g of prefs) {
            if (g && !form.selectedGenres.includes(g)) form.selectedGenres.push(g)
          }
        }
      } catch {
        /* ignore */
      }
    }
  } catch (error) {
    console.error('加载数据失败:', error)
  }
}

const onRecommend = async () => {
  if (!userStore.userInfo) {
    ElMessage.warning('请先登录')
    return
  }

  // 构建用户输入（如果选择了类型，添加到描述中）
  let userInput = form.userInput
  if (form.selectedGenres.length > 0) {
    const genreText = `我喜欢的电影类型：${form.selectedGenres.join('、')}`
    userInput = userInput ? `${genreText}。${userInput}` : genreText
  }

  try {
    // 重新推荐：先清理上次结果，再生成新结果
    recommendStore.clear()
    result.value = null
    await recommendStore.recommend({
      user_id: userStore.userInfo.id,
      user_input: userInput,
      topk_kg: form.topkKg,
      topk_rag: form.topkRag,
      favorites: form.selectedFavorites,
      with_recent: form.useRecent,
      fast_llm: false
    })
    cardPosterBroken.value = {}
    ElMessage.success('推荐完成')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '推荐失败')
    console.error(error)
  } finally {
  }
}

function buildRecUserInput(): string {
  let userInput = form.userInput
  if (form.selectedGenres.length > 0) {
    const genreText = `我喜欢的电影类型：${form.selectedGenres.join('、')}`
    userInput = userInput ? `${genreText}。${userInput}` : genreText
  }
  return userInput
}

function ragTitlesForSnapshot(r: RecommendResult): string[] {
  const raw = r.rag_movies || []
  return raw
    .map((x: any) => (typeof x === 'string' ? String(x).trim() : String(x?.name || '').trim()))
    .filter(Boolean)
}

/** 与消息中心「推荐已完成」弹窗同一套快照数据，普通用户推荐完成后展示在总结按钮下方 */
const recommendSnapshotPayload = computed((): RecommendSnapshotPayload | null => {
  const r = result.value
  if (!r || r.success === false) return null
  const hasMovies = (r.movies?.length ?? 0) > 0
  const hasText = !!(r.recommend_text && String(r.recommend_text).trim())
  const hasKg = (r.kg_movies?.length ?? 0) > 0
  const hasRag = (r.rag_movies?.length ?? 0) > 0
  const hasPeer = (r.peer_fav_movies?.length ?? 0) > 0
  if (!hasMovies && !hasText && !hasKg && !hasRag && !hasPeer) return null
  return {
    snapshot_version: 1,
    user_input: buildRecUserInput(),
    elapsed_ms: r.elapsed_ms,
    final_movies: (r.movies || []).map((m) => ({
      name: m.name,
      display: m.display,
      source: m.source
    })),
    recommend_text: r.recommend_text || '',
    kg_movies: r.kg_movies || [],
    rag_movies: ragTitlesForSnapshot(r)
  }
})

const onGenerateExplain = async () => {
  if (!userStore.userInfo) {
    ElMessage.warning('请先登录')
    return
  }
  const r = result.value
  if (!r?.kg_movies) {
    ElMessage.warning('暂无推荐上下文，请先完成推荐')
    return
  }

  const favs =
    form.selectedFavorites.length > 0
      ? form.selectedFavorites
      : favorites.value.map((f) => f.movie_name).filter(Boolean)

  try {
    await recommendStore.generateExplain({
      user_input: buildRecUserInput(),
      favorite_movies: favs,
      watched_titles: r.watched_titles || [],
      seed_movies: r.seed_movies || [],
      kg_movies: r.kg_movies || [],
      rag_movies: r.rag_movies || [],
      genre_hints: r.genre_hints || []
    })
    ElMessage.success('解读已生成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '解读生成失败')
  }
}

const onGenerateSummary = async () => {
  if (!userStore.userInfo) {
    ElMessage.warning('请先登录')
    return
  }
  if (!result.value?.movies?.length) {
    ElMessage.warning('暂无推荐结果')
    return
  }

  try {
    await recommendStore.generateSummary({ user_input: buildRecUserInput() })
    ElMessage.success('总结已生成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '总结生成失败')
  }
}

onMounted(() => {
  loadData()
  loadPlaylists()
  // 回到页面时恢复上次推荐
  if (recommendStore.last) result.value = recommendStore.last
})

/** 换账号或登出：同步清空本页展示；登入后仅保留资料里的类型倾向（由 loadData 写入） */
watch(
  () => userStore.userInfo?.id,
  async (id, prev) => {
    if (id === prev) return
    if (!userStore.userInfo) {
      favorites.value = []
      playlists.value = []
      selectedPlaylistId.value = null
      result.value = null
      return
    }
    result.value = recommendStore.last
    await loadData()
    await loadPlaylists()
  }
)
</script>

<style scoped>
.recommend-page {
  padding: 0 20px 40px;
  max-width: 1180px;
  margin: 0 auto;
  position: relative; /* 背景伪元素需要层级参照 */
  /* 与 ::before 动画共用：平移距离必须等于横向单层宽度，循环才无缝 */
  --rec-bg-tile-w: min(92vw, 1500px);
}

.rec-hero-tools {
  position: fixed;
  top: calc(64px + 8px);
  right: 16px;
  z-index: 70;
  display: flex;
  align-items: center;
  gap: 8px;
  pointer-events: auto;
}

.rec-bg-mode-toggle {
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(2, 6, 23, 0.28);
  color: rgba(255, 255, 255, 0.95);
  border-radius: 999px;
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  cursor: pointer;
  backdrop-filter: blur(12px);
  transition: transform 0.15s, background 0.15s, border-color 0.15s;
}

.rec-bg-mode-toggle:hover {
  transform: translateY(-1px);
  background: rgba(2, 6, 23, 0.36);
  border-color: rgba(255, 255, 255, 0.32);
}

.rec-bg-mode-svg {
  display: block;
  opacity: 0.96;
}

/* 推荐页两侧氛围背景（只在两侧空白显示，不影响操作） */

/* 推荐.png 横向 repeat-x，按固定宽度平移一整格后回到起点，视觉上与下一周期完全衔接 */
.recommend-page::before {
  content: '';
  position: fixed;
  inset: 64px 0 0 0;
  pointer-events: none;
  z-index: 0;
  opacity: 0.18;
  filter: brightness(1.14) contrast(1.05) saturate(1.06);
  background-image: url('/api/background/推荐.png');
  background-repeat: repeat-x;
  background-size: var(--rec-bg-tile-w) auto;
  background-position: 0 56%;
  will-change: background-position;
  animation: rec-bg-pan 120s linear infinite;
}

@keyframes rec-bg-pan {
  from {
    background-position: 0 56%;
  }
  to {
    background-position: calc(var(--rec-bg-tile-w) * -1) 56%;
  }
}

/* 关闭动态层：仅保留 page-mesh 与区块样式 */
.recommend-page--static-bg::before {
  display: none;
}

/* 确保内容层在背景之上 */
.recommend-page > * {
  position: relative;
  z-index: 1;
}

.recommend-page > .rec-hero-tools {
  position: fixed;
  z-index: 70;
}

.rec-hero {
  position: relative;
  margin: 0 -4px 24px;
  padding: 28px 32px;
  border-radius: 22px;
  overflow: hidden;
  /* 底层纯黑：小丑图偏亮/非黑底时，右侧仍能「从纯黑」再过渡到紫（与片单钢铁侠观感对齐） */
  background-color: #000;
  background-image:
    /* 最上层：仅在靠右一条窄带压回近黑，左側更早透出紫氛围，图缘仍略可辨 */
    linear-gradient(
      90deg,
      rgba(0, 0, 0, 0) 0%,
      rgba(0, 0, 0, 0) 70%,
      rgba(0, 0, 0, 0.2) 82%,
      rgba(0, 0, 0, 0.72) 92%,
      rgba(0, 0, 0, 0.94) 98%,
      #000 100%
    ),
    linear-gradient(
      90deg,
      rgba(99, 102, 241, 0.22) 0%,
      rgba(129, 140, 248, 0.16) 42%,
      rgba(168, 85, 247, 0.12) 64%,
      rgba(55, 48, 120, 0.35) 78%,
      rgba(2, 6, 23, 0.78) 90%,
      rgba(0, 0, 0, 0.88) 97%,
      rgba(0, 0, 0, 1) 100%
    ),
    radial-gradient(900px 520px at 12% 0%, rgba(99, 102, 241, 0.26), transparent 58%),
    radial-gradient(760px 480px at 44% 30%, rgba(168, 85, 247, 0.18), transparent 62%),
    linear-gradient(135deg, rgba(30, 27, 75, 0.38), rgba(0, 0, 0, 0.35));
  background-repeat: no-repeat;
  background-size: cover;
  background-position: 0 0;
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.08) inset,
    0 22px 60px rgba(0, 0, 0, 0.28);
}

.rec-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 0;
  background-image: url('/api/background/小丑.png');
  background-repeat: no-repeat;
  background-size: contain;
  background-position: 100% 50%;
  opacity: 0.28;
  filter: blur(18px) brightness(0.78) contrast(1.03) saturate(1.03);
  pointer-events: none;
  -webkit-mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 1) 0%,
    rgba(0, 0, 0, 1) 58%,
    rgba(0, 0, 0, 0.8) 66%,
    rgba(0, 0, 0, 0.28) 74%,
    rgba(0, 0, 0, 0) 86%,
    rgba(0, 0, 0, 0) 100%
  );
  mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 1) 0%,
    rgba(0, 0, 0, 1) 58%,
    rgba(0, 0, 0, 0.8) 66%,
    rgba(0, 0, 0, 0.28) 74%,
    rgba(0, 0, 0, 0) 86%,
    rgba(0, 0, 0, 0) 100%
  );
}

.rec-hero::after {
  content: '';
  position: absolute;
  inset: 0;
  z-index: 1;
  background-image: url('/api/background/小丑.png');
  background-repeat: no-repeat;
  background-size: contain;
  background-position: 100% 50%;
  opacity: 0.92;
  filter: brightness(0.86) contrast(1.05) saturate(1.03);
  pointer-events: none;
  -webkit-mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 44%,
    rgba(0, 0, 0, 0.18) 54%,
    rgba(0, 0, 0, 0.62) 62%,
    rgba(0, 0, 0, 1) 70%,
    rgba(0, 0, 0, 1) 100%
  );
  mask-image: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0) 0%,
    rgba(0, 0, 0, 0) 44%,
    rgba(0, 0, 0, 0.18) 54%,
    rgba(0, 0, 0, 0.62) 62%,
    rgba(0, 0, 0, 1) 70%,
    rgba(0, 0, 0, 1) 100%
  );
}

.rec-hero-inner {
  position: relative;
  z-index: 1;
}

.rec-hero-inner h1 {
  margin: 0 0 8px;
  font-size: clamp(1.35rem, 2.5vw, 1.75rem);
  color: rgba(255, 255, 255, 0.96);
  letter-spacing: -0.02em;
}

.rec-hero-inner p {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  color: rgba(226, 232, 240, 0.86);
  max-width: 640px;
}

.glass {
  border-radius: 20px !important;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  background: rgba(255, 255, 255, 0.08) !important;
  backdrop-filter: blur(14px);
  box-shadow: 0 22px 70px rgba(0, 0, 0, 0.24) !important;
}

.recommend-card {
  min-height: 520px;
}

.rec-card-head {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

.rec-card-head-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rec-card-title {
  font-size: 1.05rem;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.94);
  letter-spacing: -0.01em;
}

.rec-card-sub {
  font-size: 13px;
  line-height: 1.45;
  color: rgba(148, 163, 184, 0.92);
  max-width: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@media (max-width: 900px) {
  .rec-card-sub {
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
  }
}

.rec-form {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.rec-form :deep(.el-form-item) {
  margin-bottom: 0;
}

.rec-panel {
  padding: 18px 20px;
  margin-bottom: 14px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(2, 6, 23, 0.22);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.rec-panel-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}

.rec-panel-head.compact {
  margin-bottom: 10px;
}

.rec-panel-ico {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: linear-gradient(145deg, rgba(99, 102, 241, 0.35), rgba(168, 85, 247, 0.22));
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: rgba(248, 250, 252, 0.95);
  font-size: 18px;
}

.rec-panel-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.94);
}

.rec-panel-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: rgba(148, 163, 184, 0.9);
}

.rec-split {
  display: grid;
  grid-template-columns: 1fr minmax(220px, 280px);
  gap: 14px;
  margin-bottom: 14px;
  align-items: stretch;
}

@media (max-width: 900px) {
  .rec-split {
    grid-template-columns: 1fr;
  }
}

.rec-panel-grow {
  margin-bottom: 0;
}

.rec-panel-aside {
  margin-bottom: 0;
  display: flex;
  flex-direction: column;
}

.rec-textarea :deep(.el-textarea__inner) {
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(15, 23, 42, 0.45);
  color: rgba(248, 250, 252, 0.94);
}

.rec-switch-wrap {
  margin-top: auto;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.rec-switch-hint {
  margin: 0;
  font-size: 12px;
  color: rgba(148, 163, 184, 0.88);
}

.rec-sliders {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}

@media (max-width: 640px) {
  .rec-sliders {
    grid-template-columns: 1fr;
  }
}

.rec-slider-card {
  padding: 12px 14px 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(15, 23, 42, 0.35);
}

.rec-slider-top {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 4px;
}

.rec-slider-name {
  font-size: 13px;
  font-weight: 600;
  color: rgba(226, 232, 240, 0.9);
}

.rec-slider-val {
  font-size: 15px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: rgba(129, 140, 248, 0.98);
}

.rec-slider-range {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: rgba(100, 116, 139, 0.95);
}

.rec-actions {
  margin-top: 6px;
  padding: 16px 18px;
  border-radius: 16px;
  border: 1px solid rgba(99, 102, 241, 0.22);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(2, 6, 23, 0.35));
}

.rec-actions-hint {
  display: none;
}

.rec-recent-opt {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.14), rgba(2, 6, 23, 0.24));
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.rec-recent-left {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rec-recent-title {
  font-size: 13px;
  font-weight: 750;
  color: rgba(248, 250, 252, 0.94);
}

.rec-recent-desc {
  font-size: 12px;
  line-height: 1.45;
  color: rgba(148, 163, 184, 0.92);
}

.rec-recent-switch :deep(.el-switch__core) {
  background: rgba(15, 23, 42, 0.55);
  border-color: rgba(255, 255, 255, 0.14);
}

.rec-cta {
  min-width: 200px;
  padding-left: 28px;
  padding-right: 28px;
}

.rec-cta-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.rec-inline-progress {
  font-weight: 500;
  color: rgba(148, 163, 184, 0.92);
  background: transparent;
  border: none;
  padding: 0;
  border-radius: 0;
}

.rec-inline-progress-sub {
  color: rgba(148, 163, 184, 0.72);
  font-weight: 450;
}

.rec-progress-bar {
  margin-top: 12px;
}

.rec-error-alert {
  margin: 16px 0;
}

.rec-cta.alt {
  min-width: 160px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  background: rgba(2, 6, 23, 0.22);
  color: rgba(248, 250, 252, 0.92);
}

.rec-cta.alt:hover {
  border-color: rgba(99, 102, 241, 0.4);
  background: rgba(2, 6, 23, 0.3);
}

.genre-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 10px;
}

.rec-form :deep(.rec-genre-chip) {
  margin-right: 0 !important;
  padding: 8px 12px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(2, 6, 23, 0.18);
}

.rec-form :deep(.rec-genre-chip .el-checkbox__inner) {
  border-color: rgba(255, 255, 255, 0.18);
  background: rgba(15, 23, 42, 0.55);
}

.rec-form :deep(.rec-genre-chip.is-checked .el-checkbox__inner) {
  background: rgba(99, 102, 241, 0.9);
  border-color: rgba(99, 102, 241, 0.9);
}

.rec-form :deep(.rec-genre-chip .el-checkbox__label) {
  color: rgba(226, 232, 240, 0.92);
}

.rec-form :deep(.rec-genre-chip.is-checked .el-checkbox__label) {
  color: rgba(248, 250, 252, 0.96);
}

.rec-form :deep(.rec-genre-chip:hover) {
  border-color: rgba(99, 102, 241, 0.35);
}

.rec-textarea :deep(.el-input__count) {
  background: transparent !important;
}

.rec-textarea :deep(.el-input__count-inner) {
  background: rgba(2, 6, 23, 0.35) !important;
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: rgba(203, 213, 225, 0.9);
  border-radius: 10px;
  padding: 0 8px;
  height: 22px;
  line-height: 22px;
  backdrop-filter: blur(10px);
}

.favorites-selector {
  width: 100%;
}

.favorites-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
  width: 100%;
}

.favorite-item {
  margin-right: 0 !important;
  padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  background: rgba(2, 6, 23, 0.28);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.favorite-item:hover {
  border-color: rgba(99, 102, 241, 0.45);
  box-shadow: 0 8px 22px rgba(99, 102, 241, 0.15);
}

.rec-form :deep(.favorite-item .el-checkbox__inner) {
  border-color: rgba(255, 255, 255, 0.18);
  background: rgba(15, 23, 42, 0.55);
}

.rec-form :deep(.favorite-item.is-checked .el-checkbox__inner) {
  background: rgba(99, 102, 241, 0.9);
  border-color: rgba(99, 102, 241, 0.9);
}

.rec-form :deep(.favorite-item .el-checkbox__label) {
  color: rgba(226, 232, 240, 0.92);
}

.rec-form :deep(.favorite-item.is-checked .el-checkbox__label) {
  color: rgba(248, 250, 252, 0.96);
}

.favorite-info {
  display: flex;
  flex-direction: column;
}

.movie-name {
  font-weight: 500;
  margin-bottom: 4px;
  color: rgba(248, 250, 252, 0.94);
}

.genres {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.9);
}

.empty-favorites {
  padding: 20px;
}

.result-section {
  margin-top: 20px;
}

.result-section :deep(.el-divider__text) {
  color: rgba(248, 250, 252, 0.92);
  font-weight: 700;
  background: transparent;
}

.llm-explain-section {
  margin-bottom: 24px;
}

.llm-explain-section h3 {
  margin-bottom: 8px;
  color: rgba(248, 250, 252, 0.94);
}

.llm-disclaimer {
  font-size: 13px;
  color: #909399;
  margin: 0 0 12px 0;
  line-height: 1.5;
}

.llm-explain-card {
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(2, 6, 23, 0.28);
}

.llm-explain-text {
  white-space: pre-wrap;
  line-height: 1.75;
  color: rgba(226, 232, 240, 0.92);
  font-size: 14px;
}

.llm-error-alert {
  margin-bottom: 20px;
}

.llm-summary-section {
  margin: 18px 0 24px;
}

.llm-summary-section h3 {
  margin-bottom: 8px;
  color: rgba(255, 255, 255, 0.92);
}

.llm-summary-card {
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(2, 6, 23, 0.22);
}

.llm-summary-text {
  white-space: pre-wrap;
  line-height: 1.8;
  color: rgba(226, 232, 240, 0.9);
  font-size: 14px;
}

.llm-summary-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin: 18px 0 10px;
}

.llm-summary-hint {
  font-size: 13px;
  color: rgba(148, 163, 184, 0.92);
  line-height: 1.5;
  max-width: 720px;
}

.rec-snapshot-embed-wrap {
  margin: 8px 0 20px;
}

.rec-snapshot-embed-h {
  margin: 0 0 10px;
  font-size: 16px;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.94);
}

.admin-pipeline-preamble {
  margin-bottom: 16px;
}
.admin-pref-decompose {
  margin-bottom: 18px;
}
.admin-pref-line {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(226, 232, 240, 0.92);
}

.admin-pref-chips {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.admin-pref-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.admin-pref-map {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.admin-pref-map-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.admin-pref-map-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

.admin-pref-map-zh {
  color: rgba(196, 181, 253, 0.96);
  font-weight: 600;
}

.admin-pref-map-arrow {
  color: rgba(148, 163, 184, 0.9);
}

.admin-pref-map-en {
  color: rgba(191, 219, 254, 0.92);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  word-break: break-word;
}
.admin-pref-k {
  display: inline-block;
  min-width: 96px;
  margin-right: 8px;
  color: rgba(165, 180, 252, 0.88);
  font-weight: 600;
}
.raw-list-legend {
  margin: 0;
  padding: 6px 14px 0;
  font-size: 11px;
  color: rgba(148, 163, 184, 0.95);
}
.raw-list-legend .lg-final {
  color: #34d399;
  margin-right: 4px;
}
.raw-list-legend .lg-pool {
  color: rgba(148, 163, 184, 0.85);
  margin: 0 4px 0 10px;
}
.raw-list-legend .lg-note {
  color: rgba(148, 163, 184, 0.75);
  margin-left: 10px;
}
.raw-list-kg li.kg-raw-final {
  color: #6ee7b7;
  font-weight: 650;
}
.raw-list-kg li.kg-raw-pool {
  color: rgba(148, 163, 184, 0.88);
}
.raw-list-card.rag li.rag-raw-final {
  color: #6ee7b7;
  font-weight: 650;
}
.raw-list-card.rag li.rag-raw-pool {
  color: rgba(148, 163, 184, 0.88);
}

/* —— 管理员 · 推理过程 —— */
.admin-insight {
  margin-top: 28px;
  padding: 22px 22px 8px;
  border-radius: 20px;
  border: 1px solid rgba(129, 140, 248, 0.28);
  background: linear-gradient(145deg, rgba(15, 23, 42, 0.55), rgba(30, 27, 75, 0.35));
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.25);
}

.admin-insight-head {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.admin-insight-icon {
  font-size: 28px;
  color: #a5b4fc;
  margin-top: 2px;
}

.admin-insight-title {
  margin: 0 0 4px;
  font-size: 1.12rem;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.96);
  letter-spacing: -0.02em;
}

.admin-insight-sub {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(199, 210, 254, 0.78);
}

.glass-inner {
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  background: rgba(2, 6, 23, 0.22);
  overflow: hidden;
}

.admin-collapse :deep(.el-collapse-item__header) {
  padding: 14px 18px;
  font-weight: 600;
  color: rgba(248, 250, 252, 0.94);
  background: rgba(15, 23, 42, 0.35);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.admin-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(2, 6, 23, 0.12);
}

.admin-collapse :deep(.el-collapse-item__content) {
  padding: 18px 18px 22px;
  color: rgba(226, 232, 240, 0.9);
}

.admin-collapse :deep(.el-collapse-item__arrow) {
  color: rgba(199, 210, 254, 0.85);
}

.collapse-title-row {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.collapse-title-row .el-icon {
  font-size: 18px;
  color: #a5b4fc;
}

.collapse-count {
  margin-left: 6px;
  border-color: rgba(165, 180, 252, 0.45) !important;
  color: #c7d2fe !important;
}

.pipeline-track {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.pipe-step {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.pipe-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 28px;
  flex-shrink: 0;
  align-self: stretch;
}

.pipe-line {
  width: 2px;
  flex: 0 0 auto;
  background: linear-gradient(180deg, rgba(129, 140, 248, 0.5), rgba(99, 102, 241, 0.25));
  border-radius: 2px;
}

.pipe-line-before {
  min-height: 12px;
  height: 12px;
}

.pipe-line-after {
  flex: 1 1 auto;
  min-height: 8px;
}

.pipe-dot {
  width: 32px;
  height: 32px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(30, 41, 59, 0.9);
  color: #94a3b8;
}

.pipe-dot.st-ok {
  color: #4ade80;
  border-color: rgba(74, 222, 128, 0.35);
  background: rgba(22, 101, 52, 0.25);
}

.pipe-dot.st-warn {
  color: #fbbf24;
  border-color: rgba(251, 191, 36, 0.4);
  background: rgba(120, 53, 15, 0.22);
}

.pipe-dot.st-error {
  color: #f87171;
  border-color: rgba(248, 113, 113, 0.4);
  background: rgba(127, 29, 29, 0.22);
}

.pipe-card {
  flex: 1;
  margin-bottom: 14px;
  padding: 12px 14px 14px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(15, 23, 42, 0.45);
}

.pipe-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.pipe-card-top-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.pipe-step-title {
  font-weight: 650;
  font-size: 14px;
  color: rgba(248, 250, 252, 0.96);
  line-height: 1.35;
}

.pipe-ms {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: rgba(167, 139, 250, 0.95);
  white-space: nowrap;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(99, 102, 241, 0.18);
  border: 1px solid rgba(99, 102, 241, 0.28);
  flex-shrink: 0;
  margin-top: 1px;
}

.pipe-llm-tag {
  flex-shrink: 0;
}

.rec-phase-tag {
  margin-left: 10px;
  vertical-align: middle;
}

.kg-stage-sub {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(148, 163, 184, 0.95);
}

.pipe-step-msg {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: rgba(203, 213, 225, 0.92);
}

.pipe-step-msg .pipe-step-id {
  display: inline;
  margin-left: 8px;
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 11px;
  font-family: var(--mono, ui-monospace, monospace);
  color: rgba(148, 163, 184, 0.88);
  letter-spacing: 0.02em;
  background: rgba(15, 23, 42, 0.45);
  border: 1px solid rgba(148, 163, 184, 0.2);
  vertical-align: baseline;
}

.kg-panel {
  margin-bottom: 18px;
}

.kg-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(165, 180, 252, 0.85);
  margin-bottom: 8px;
}

.kg-method-block {
  margin-bottom: 16px;
}

.kg-method {
  margin: 0;
  font-size: 13px;
  line-height: 1.65;
  color: rgba(226, 232, 240, 0.92);
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(2, 6, 23, 0.35);
  font-family: var(--mono, ui-monospace, Consolas, monospace);
}

.kg-stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.kg-stat {
  flex: 1 1 120px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(30, 27, 75, 0.25);
}

.kg-stat.wide {
  flex: 1 1 200px;
}

.kg-stat-k {
  display: block;
  font-size: 11px;
  color: rgba(199, 210, 254, 0.72);
  margin-bottom: 4px;
}

.kg-stat-v {
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: #e9d5ff;
}

.kg-chip-block {
  margin-bottom: 14px;
}

.kg-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.kg-chip {
  border-radius: 999px !important;
  border-color: rgba(165, 180, 252, 0.35) !important;
  color: #e0e7ff !important;
  background: rgba(99, 102, 241, 0.12) !important;
}

.kg-chip.pref {
  border-color: rgba(56, 189, 248, 0.35) !important;
}

.kg-weight-grid {
  margin-bottom: 16px;
}

.kg-weights {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kg-weight-row {
  display: grid;
  grid-template-columns: 88px 1fr 44px;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}

.kg-w-name {
  color: rgba(226, 232, 240, 0.88);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kg-w-bar-wrap {
  height: 8px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.85);
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.kg-w-bar {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #6366f1, #a855f7);
  min-width: 4px;
  transition: width 0.35s ease;
}

.kg-w-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: rgba(196, 181, 253, 0.95);
}

.kg-note p {
  margin: 0;
  font-size: 13px;
  line-height: 1.65;
  color: rgba(203, 213, 225, 0.9);
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(15, 23, 42, 0.35);
}

.raw-lists-row {
  margin-top: 4px;
}

.raw-list-card {
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(2, 6, 23, 0.32);
  overflow: hidden;
  min-height: 220px;
  max-height: 320px;
  display: flex;
  flex-direction: column;
}

.raw-list-card.rag {
  border-color: rgba(52, 211, 153, 0.2);
}

.raw-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  font-size: 13px;
  font-weight: 650;
  color: rgba(248, 250, 252, 0.94);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(15, 23, 42, 0.4);
}

.raw-list {
  margin: 0;
  padding: 12px 14px 14px 28px;
  overflow-y: auto;
  flex: 1;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(226, 232, 240, 0.9);
}

.raw-list li {
  margin-bottom: 8px;
}

.raw-sim {
  margin-left: 6px;
  font-size: 11px;
  color: rgba(52, 211, 153, 0.9);
  font-variant-numeric: tabular-nums;
}

.peer-fav-card .peer-w {
  color: rgba(147, 197, 253, 0.95);
}

.raw-empty {
  padding: 36px 16px;
  text-align: center;
  font-size: 13px;
  color: rgba(148, 163, 184, 0.85);
}

.rule-text-panel {
  border-radius: 14px;
  border: 1px solid rgba(129, 140, 248, 0.22);
  background: rgba(2, 6, 23, 0.35);
  overflow: hidden;
}

.rule-text-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(15, 23, 42, 0.45);
}

.rule-hint {
  font-size: 12px;
  color: rgba(199, 210, 254, 0.78);
}

.btn-ic {
  margin-right: 4px;
  vertical-align: middle;
}

.rule-text-body {
  margin: 0;
  padding: 16px 16px 18px;
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--mono, ui-monospace, Consolas, monospace);
  font-size: 12.5px;
  line-height: 1.7;
  color: rgba(226, 232, 240, 0.92);
}

.merged-block {
  margin-bottom: 28px;
}

.merged-head h3 {
  margin: 0 0 6px;
  font-size: 1.15rem;
  color: rgba(248, 250, 252, 0.96);
}

.merged-hint {
  font-size: 13px;
  color: rgba(203, 213, 225, 0.82);
  margin: 0 0 18px;
  line-height: 1.5;
}

.merged-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.pl-select {
  width: 200px;
}
.pl-hint {
  font-size: 12px;
  font-weight: 700;
  color: rgba(203, 213, 225, 0.78);
}

.rec-card-strip {
  display: flex;
  gap: 14px;
  overflow-x: auto;
  padding-bottom: 8px;
  scroll-snap-type: x mandatory;
}

.rec-ntfx-strip {
  padding-top: 4px;
}

.rec-ntfx-card {
  flex: 0 0 min(300px, 88vw);
  scroll-snap-align: start;
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: #050508;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.35);
}

.rec-ntfx-stack {
  position: relative;
  min-height: min(420px, 78vh);
  width: 100%;
}

.rec-ntfx-cover {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.rec-ntfx-cover-ph {
  background: linear-gradient(145deg, #1e293b, #0f172a);
}

.rec-ntfx-blur-band {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 55%;
  pointer-events: none;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  mask-image: linear-gradient(to top, #000 0%, #000 35%, transparent 100%);
  -webkit-mask-image: linear-gradient(to top, #000 0%, #000 35%, transparent 100%);
}

.rec-ntfx-scrim {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(
    to top,
    rgba(3, 7, 18, 0.98) 0%,
    rgba(3, 7, 18, 0.78) 38%,
    rgba(3, 7, 18, 0.28) 62%,
    transparent 85%
  );
}

.rec-ntfx-rank {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 2;
  min-width: 30px;
  height: 30px;
  padding: 0 8px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: 13px;
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(8px);
}

.rec-ntfx-content {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2;
  padding: 16px 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rec-ntfx-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 750;
  line-height: 1.35;
  color: rgba(248, 250, 252, 0.96);
}

.rec-ntfx-year {
  font-size: 0.8rem;
  font-weight: 450;
  color: rgba(148, 163, 184, 0.72);
  margin-left: 6px;
}

.rec-ntfx-meta-line {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
  color: rgba(203, 213, 225, 0.88);
}

.rec-ntfx-lbl {
  display: inline-block;
  min-width: 36px;
  margin-right: 8px;
  font-weight: 700;
  color: rgba(148, 163, 184, 0.95);
}

.rec-ntfx-blurb {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(226, 232, 240, 0.92);
  display: -webkit-box;
  line-clamp: 6;
  -webkit-line-clamp: 6;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 分享预览弹窗：独立深色玻璃风，不与影片详情 detail-dialog 共用 */
.share-listicle-dialog {
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid rgba(129, 140, 248, 0.22);
  background: rgba(15, 23, 42, 0.92);
  backdrop-filter: blur(18px) saturate(1.12);
  -webkit-backdrop-filter: blur(18px) saturate(1.12);
  box-shadow: 0 28px 90px rgba(0, 0, 0, 0.4);
  padding: 0;
  --el-dialog-padding-primary: 0;
}

.share-listicle-dialog :deep(.el-dialog__header) {
  margin: 0;
  padding: 0;
  background: transparent;
}

/* 顶栏：一行，左标题右关闭 */
.share-listicle-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}

.share-listicle-head-title {
  min-width: 0;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.35;
  color: #0f172a;
}

.share-listicle-head-close {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #ffffff;
  color: #64748b;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
}

.share-listicle-head-close:hover {
  background: #f1f5f9;
  border-color: #94a3b8;
  color: #334155;
}

.share-listicle-head-close:active {
  background: #e2e8f0;
}

.share-listicle-dialog .dlg {
  padding: 8px 0 4px;
}

.share-listicle-iframe {
  width: 100%;
  height: min(72vh, 640px);
  border: none;
  border-radius: 12px;
  background: #faf7f2;
}

.share-listicle-dialog .share-listicle-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  width: 100%;
}

.share-listicle-dialog .dlg-save {
  height: 36px;
  padding: 0 20px;
}

/* 弹窗主体背景对齐系统主题（深色框 + 内嵌浅色预览） */
.share-listicle-dialog :deep(.el-dialog__body) {
  background:
    radial-gradient(900px 380px at 10% 0%, rgba(99, 102, 241, 0.16), transparent 55%),
    radial-gradient(900px 380px at 85% 10%, rgba(139, 92, 246, 0.14), transparent 55%),
    rgba(2, 6, 23, 0.92);
  padding: 14px 18px 12px;
}

.share-listicle-dialog :deep(.el-dialog__footer) {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 12px 18px 16px;
  margin: 0;
  background: linear-gradient(180deg, #f1f5f9 0%, #e8edf4 100%);
  border-top: 1px solid rgba(148, 163, 184, 0.28);
}

.user-llm h3 {
  font-size: 16px;
}

.recommend-card :deep(.el-input__wrapper),
.recommend-card :deep(.el-textarea__inner) {
  background: rgba(2, 6, 23, 0.25);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
}

.recommend-card :deep(.el-divider) {
  border-color: rgba(255, 255, 255, 0.1);
}

</style>
