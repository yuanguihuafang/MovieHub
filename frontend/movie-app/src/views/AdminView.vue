<template>
  <div class="admin-container page-mesh">
    <el-card class="admin-card glass-admin" shadow="never">
      <template #header>
        <div class="card-header">
          <span>🛠️ 管理后台</span>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <!-- 系统概览（默认） -->
        <el-tab-pane label="🔬 系统概览" name="stats">
          <div class="action-bar">
            <el-button type="primary" :icon="Refresh" @click="onRefreshStatsTab">刷新概览</el-button>
          </div>

          <div class="overview-grid" style="margin-top: 18px">
            <div class="ov-card">
              <div class="ov-k">用户总数</div>
              <div class="ov-v">{{ overview.counts.users }}</div>
            </div>
            <div class="ov-card">
              <div class="ov-k">收藏总数</div>
              <div class="ov-v">{{ overview.counts.favorites }}</div>
            </div>
            <div class="ov-card">
              <div class="ov-k">已看过总数</div>
              <div class="ov-v">{{ overview.counts.watched }}</div>
            </div>
            <div class="ov-card">
              <div class="ov-k">浏览记录总数</div>
              <div class="ov-v">{{ overview.counts.browse_history }}</div>
            </div>
            <div class="ov-card">
              <div class="ov-k">推荐日志总数</div>
              <div class="ov-v">{{ overview.counts.recommend_logs }}</div>
            </div>
            <div class="ov-card wide">
              <div class="ov-k">关键运行状态</div>
              <div class="ov-status">
                <el-tag size="small" effect="plain" round :type="overview.runtime.tmdb_configured ? 'success' : 'warning'">
                  TMDB {{ overview.runtime.tmdb_configured ? '已配置' : '未配置' }}
                </el-tag>
                <el-tag size="small" effect="plain" round :type="overview.runtime.kg_loaded ? 'success' : 'info'">
                  KG {{ overview.runtime.kg_loaded ? '已加载' : '未加载' }}
                </el-tag>
                <el-tag size="small" effect="plain" round :type="overview.runtime.rag_loaded ? 'success' : 'info'">
                  RAG {{ overview.runtime.rag_loaded ? '已加载' : '未加载' }}
                </el-tag>
                <el-tag
                  size="small"
                  effect="plain"
                  round
                  :type="overview.runtime.poster_cache_enabled ? 'success' : 'info'"
                >
                  海报缓存 {{ overview.runtime.poster_cache_enabled ? '启用' : '关闭' }}
                </el-tag>
                <span class="ov-path">缓存目录：{{ overview.runtime.poster_cache_root || '—' }}</span>
              </div>
            </div>
          </div>

          <div class="overview-grid overview-grid--sys" style="margin-top: 14px">
            <div class="ov-card">
              <div class="ov-k">豆瓣 CSV 影片</div>
              <div class="ov-v">{{ overview.system?.douban_movie_count ?? 0 }}</div>
            </div>
            <div class="ov-card">
              <div class="ov-k">TMDB CSV 已加载</div>
              <div class="ov-v">{{ overview.system?.tmdb_csv_movie_count ?? 0 }}</div>
            </div>
            <div class="ov-card">
              <div class="ov-k">RAG 向量条目</div>
              <div class="ov-v">{{ overview.system?.rag_document_count ?? 0 }}</div>
            </div>
          </div>
          <div class="ov-card ov-tmdb-home" style="margin-top: 12px">
            <div class="ov-k">TMDB 正在热映 / 即将上映 · 本地缓存上次更新</div>
            <div class="ov-line">{{ overview.system?.tmdb_home_last_refresh_display || '—' }}</div>
            <div class="ov-path" style="margin-top: 8px">
              {{ overview.system?.tmdb_home_note || '' }}
            </div>
          </div>

          <el-card class="nested-glass kg-eval-card" shadow="never" style="margin-top: 20px">
            <template #header>
              <div class="kg-eval-head">
                <span>📐 模型评估指标</span>
                <el-button type="primary" link size="small" @click="loadKgEvalDisplay">刷新</el-button>
              </div>
            </template>
            <el-alert
              v-if="!kgEvalConfigured"
              type="info"
              :closable="false"
              show-icon
              :title="kgEvalMessage || '未配置 kg_eval_display.json'"
            />
            <template v-else>
              <div class="kg-eval-title">{{ kgEvalPayload?.title || '评估指标' }}</div>
              <p v-if="kgEvalPayload?.task" class="kg-eval-meta">{{ kgEvalPayload.task }}</p>
              <p v-if="kgEvalPayload?.source" class="kg-eval-meta muted">{{ kgEvalPayload.source }}</p>
              <div v-if="kgEvalMetricsRows.length" class="kg-eval-metrics">
                <div v-for="row in kgEvalMetricsRows" :key="row.k" class="kg-eval-metric">
                  <div class="kg-eval-mk">{{ row.k }}</div>
                  <div class="kg-eval-mv">{{ row.v }}</div>
                </div>
              </div>
              <div v-if="kgEvalBaselines.length" class="kg-eval-baseline-wrap">
                <div class="kg-eval-subh">与基线对比</div>
                <el-table
                  :data="kgEvalBaselines"
                  class="admin-table kg-baseline-table"
                  size="small"
                  :row-class-name="kgBaselineRowClass"
                >
                  <el-table-column prop="name" label="模型" min-width="140" />
                  <el-table-column label="Hits@1" width="100" align="right">
                    <template #default="{ row }">
                      {{ formatKgMetricCell(row['Hits@1']) }}
                    </template>
                  </el-table-column>
                  <el-table-column label="Hits@3" width="100" align="right">
                    <template #default="{ row }">
                      {{ formatKgMetricCell(row['Hits@3']) }}
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </template>
          </el-card>

          <el-row :gutter="20" style="margin-top: 20px">
            <el-col :span="12">
              <el-card class="nested-glass" shadow="never">
                <template #header>
                  <span>推荐与日志概况</span>
                </template>
                <el-table :data="modelStatsView" class="admin-table" style="width: 100%">
                  <el-table-column prop="call_type" label="调用类型" />
                  <el-table-column prop="count" label="次数" width="100" />
                  <el-table-column prop="avg_s" label="平均耗时(s)" width="120" />
                </el-table>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card class="nested-glass" shadow="never">
                <template #header>
                  <span>最近调用记录</span>
                </template>
                <div class="recent-logs-scroll">
                  <el-table :data="modelLogsView" class="admin-table" style="width: 100%">
                    <el-table-column prop="created_at" label="时间" width="160" />
                    <el-table-column prop="username" label="用户" width="100" />
                    <el-table-column prop="call_type" label="类型" min-width="160" />
                    <el-table-column prop="elapsed_s" label="耗时(s)" width="100" />
                  </el-table>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </el-tab-pane>

        <!-- 用户管理 -->
        <el-tab-pane label="👥 用户管理" name="users">
          <div class="action-bar">
            <el-button type="success" @click="openCreateUser">新建用户</el-button>
            <el-button type="primary" :icon="Refresh" @click="loadUsers">
              刷新用户列表
            </el-button>
          </div>

          <el-table :data="users" class="admin-table admin-table--fill" style="width: 100%; margin-top: 20px">
            <el-table-column prop="id" label="ID" width="72" align="center" />
            <el-table-column prop="username" label="用户名" min-width="140" show-overflow-tooltip />
            <el-table-column prop="role" label="角色" width="108" align="center">
              <template #default="{ row }">
                <el-tag :type="row.role === 'admin' ? 'danger' : 'primary'">
                  {{ row.role }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="注册时间" min-width="168" />
            <el-table-column prop="review_muted_until" label="禁言至" min-width="168" show-overflow-tooltip />
            <el-table-column label="操作" min-width="268" align="right" fixed="right">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="primary"
                  @click="showEditUserDialog(row)"
                >
                  编辑
                </el-button>
                <el-button size="small" plain @click="openMute(row.id)">禁言/解禁</el-button>
                <el-button
                  size="small"
                  type="danger"
                  @click="deleteUser(row.id)"
                  :disabled="row.role === 'admin'"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 收藏管理 -->
        <el-tab-pane label="⭐ 收藏管理" name="favorites">
          <div class="action-bar">
            <el-input
              v-model="favUsername"
              clearable
              placeholder="用户名（模糊查询，留空为全部）"
              style="width: 280px; margin-right: 10px"
              @keyup.enter="loadFavorites"
            />
            <el-button type="primary" :icon="Refresh" @click="loadFavorites">
              查询
            </el-button>
          </div>

          <el-table :data="favorites" class="admin-table admin-table--fill admin-fav-table" style="width: 100%; margin-top: 20px">
            <el-table-column prop="username" label="用户名" min-width="120" show-overflow-tooltip />
            <el-table-column prop="movie_name" label="电影" min-width="160" show-overflow-tooltip />
            <el-table-column prop="genres" label="类型" min-width="130" show-overflow-tooltip />
            <el-table-column prop="added_at" label="收藏时间" min-width="172" />
            <el-table-column label="操作" width="104" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="danger"
                  @click="deleteFavorite(row.id)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 推荐日志 -->
        <el-tab-pane label="📊 推荐日志" name="logs">
          <div class="action-bar">
            <el-button type="primary" :icon="Refresh" @click="loadRecommendLogs">
              刷新日志
            </el-button>
          </div>

          <el-table :data="recommendLogs" class="admin-table admin-table--fill" style="width: 100%; margin-top: 20px">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="log-expand">
                  <!-- 推理流水线（与线上推荐页 pipeline 一致） -->
                  <div
                    v-if="row.inference_meta?.pipeline?.length"
                    class="inf-section"
                  >
                    <div class="inf-section-title">推理流水线（LLM 步骤带 <span class="inf-llm-inline">LLM</span> 标识）</div>
                    <div class="inf-pipeline">
                      <div
                        v-for="(st, si) in row.inference_meta.pipeline"
                        :key="(st.id || '') + '-' + si"
                        class="inf-step"
                        :class="{ 'inf-step--llm': st.call_kind === 'llm' }"
                      >
                        <div class="inf-step-head">
                          <el-tag size="small" :type="pipelineStatusTagType(st.status)">
                            {{ st.status || '—' }}
                          </el-tag>
                          <el-tag
                            v-if="st.call_kind === 'llm'"
                            size="small"
                            type="warning"
                            effect="dark"
                            class="inf-llm-mark"
                          >
                            LLM
                          </el-tag>
                          <span class="inf-step-title">{{ st.title }}</span>
                          <span v-if="st.elapsed_ms != null && st.elapsed_ms > 0" class="inf-step-ms">
                            {{ formatStepMs(st.elapsed_ms) }}
                          </span>
                        </div>
                        <div v-if="st.message" class="inf-step-msg">{{ st.message }}</div>
                      </div>
                    </div>
                  </div>

                  <!-- 图谱 Multi_MoE 元信息 -->
                  <div
                    v-if="hasKgMeta(row.inference_meta)"
                    class="inf-section inf-kg-block"
                  >
                    <div class="inf-section-title">图谱 · Multi_MoE 元信息</div>
                    <div class="inf-kg-inner">
                      <p v-if="row.inference_meta.kg_model_meta.method" class="inf-mono-line">
                        {{ row.inference_meta.kg_model_meta.method }}
                      </p>
                      <div v-if="row.inference_meta.kg_model_meta.note" class="inf-note">
                        {{ row.inference_meta.kg_model_meta.note }}
                      </div>
                      <div
                        v-if="(row.inference_meta.kg_model_meta.relations_used || []).length"
                        class="inf-kv"
                      >
                        <span class="inf-k">参与关系</span>
                        <span class="inf-v">{{
                          (row.inference_meta.kg_model_meta.relations_used || []).join('、')
                        }}</span>
                      </div>
                      <div
                        v-if="row.inference_meta.kg_model_meta.genre_boost != null"
                        class="inf-kv"
                      >
                        <span class="inf-k">genre 加权</span>
                        <span class="inf-v">×{{ row.inference_meta.kg_model_meta.genre_boost }}</span>
                      </div>
                      <div
                        v-if="
                          row.inference_meta.kg_model_meta.relation_weights &&
                          Object.keys(row.inference_meta.kg_model_meta.relation_weights).length
                        "
                        class="inf-rw-wrap"
                      >
                        <div class="inf-k">关系权重（节选）</div>
                        <div class="inf-rw-grid">
                          <span
                            v-for="[rk, rv] in Object.entries(
                              row.inference_meta.kg_model_meta.relation_weights || {}
                            ).slice(0, 14)"
                            :key="rk"
                            class="inf-rw-item"
                          >
                            <code>{{ rk }}</code> {{ rv }}
                          </span>
                        </div>
                      </div>
                      <p
                        v-if="row.inference_meta.kg_model_meta.flow_summary"
                        class="inf-flow-sum"
                      >
                        {{ row.inference_meta.kg_model_meta.flow_summary }}
                      </p>
                    </div>
                  </div>

                  <!-- 种子与偏好（结构化） -->
                  <div
                    v-if="
                      (row.inference_meta?.seed_movies || []).length ||
                      (row.inference_meta?.genre_hints || []).length
                    "
                    class="inf-section"
                  >
                    <div class="inf-section-title">种子与偏好提示</div>
                    <div v-if="(row.inference_meta.seed_movies || []).length" class="inf-kv">
                      <span class="inf-k">图谱种子实体</span>
                      <span class="inf-v inf-seeds">{{
                        (row.inference_meta.seed_movies || []).map(displayTitle).join('、')
                      }}</span>
                    </div>
                    <div v-if="(row.inference_meta.genre_hints || []).length" class="inf-kv">
                      <span class="inf-k">类型 hints</span>
                      <span class="inf-v">{{ (row.inference_meta.genre_hints || []).join('、') }}</span>
                    </div>
                    <div
                      v-if="prefDecomposeSummary(row.inference_meta.preference_decompose)"
                      class="inf-pref-preview"
                    >
                      {{ prefDecomposeSummary(row.inference_meta.preference_decompose) }}
                    </div>
                  </div>

                  <!-- 大模型调用（与 llm_invocations 一致） -->
                  <div
                    v-if="(row.inference_meta?.llm_invocations || []).length"
                    class="inf-section"
                  >
                    <div class="inf-section-title">
                      大模型调用摘要 <el-tag size="small" type="warning" effect="dark" class="inf-llm-mark">LLM</el-tag>
                    </div>
                    <el-table
                      :data="row.inference_meta.llm_invocations"
                      size="small"
                      class="inf-llm-table"
                      border
                    >
                      <el-table-column prop="step_id" label="步骤 ID" width="120" show-overflow-tooltip />
                      <el-table-column prop="title" label="说明" min-width="160" show-overflow-tooltip />
                      <el-table-column prop="status" label="状态" width="88" />
                      <el-table-column prop="elapsed_ms" label="耗时(ms)" width="100" align="right" />
                    </el-table>
                  </div>

                  <div class="log-block">
                    <div class="log-k">最终推荐</div>
                    <div class="log-v">
                      <el-tag
                        v-for="(m, idx) in (row.final_movies || []).slice(0, 28)"
                        :key="m + idx"
                        size="small"
                        effect="plain"
                        round
                        class="log-tag"
                      >
                        {{ displayTitle(m) }}
                      </el-tag>
                      <span v-if="(row.final_movies || []).length > 28" class="log-more">
                        … 还有 {{ (row.final_movies || []).length - 28 }} 部
                      </span>
                      <el-empty
                        v-if="!(row.final_movies || []).length"
                        description="该条日志未记录最终推荐列表（旧版本数据）"
                        :image-size="48"
                      />
                    </div>
                  </div>

                  <div v-if="row.recommend_text" class="log-block">
                    <div class="log-k">推荐文本（片段）</div>
                    <div class="log-v log-text">{{ row.recommend_text }}</div>
                  </div>

                  <div class="log-grid log-grid--triple">
                    <div class="log-mini">
                      <div class="log-k">图谱候选（KG 实体短名）</div>
                      <div class="log-v">
                        <el-tag
                          v-for="(m, idx) in (row.kg_movies || []).slice(0, 30)"
                          :key="String(m) + idx"
                          size="small"
                          effect="plain"
                          round
                          class="log-tag"
                          :type="isFinalPicked(row, displayTitle(String(m))) ? 'success' : 'info'"
                        >
                          {{ displayTitle(String(m)) }}
                        </el-tag>
                        <span v-if="!(row.kg_movies || []).length" class="inf-snap-none">—</span>
                      </div>
                    </div>
                    <div class="log-mini">
                      <div class="log-k">片库检索候选（RAG / 豆瓣）</div>
                      <div class="log-v">
                        <el-tag
                          v-for="(m, idx) in (row.rag_movies || []).slice(0, 30)"
                          :key="String(m) + idx"
                          size="small"
                          effect="plain"
                          round
                          class="log-tag"
                          :type="isFinalPicked(row, displayTitle(String(m))) ? 'success' : 'info'"
                        >
                          {{ displayTitle(String(m)) }}
                        </el-tag>
                        <span v-if="!(row.rag_movies || []).length" class="inf-snap-none">—</span>
                      </div>
                    </div>
                    <div class="log-mini">
                      <div class="log-k">同偏好 · 他人收藏候选</div>
                      <div class="log-v">
                        <el-tag
                          v-for="(m, idx) in peerFavCandidates(row).slice(0, 30)"
                          :key="peerFavKey(m, idx)"
                          size="small"
                          effect="plain"
                          round
                          class="log-tag"
                          :type="
                            isFinalPicked(row, displayTitle(peerFavTitle(m))) ? 'success' : 'info'
                          "
                        >
                          {{ displayTitle(peerFavTitle(m)) }}
                        </el-tag>
                        <span v-if="!peerFavCandidates(row).length" class="inf-snap-none">—</span>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="160" />
            <el-table-column prop="username" label="用户" width="120" />
            <el-table-column prop="user_input" label="输入" min-width="150" show-overflow-tooltip />
            <el-table-column label="推理快照" width="92" align="center">
              <template #default="{ row }">
                <el-tag
                  v-if="row.inference_meta?.pipeline?.length"
                  size="small"
                  type="success"
                  effect="plain"
                >
                  有
                </el-tag>
                <span v-else class="inf-snap-none">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="kg_count" label="图谱条数" width="100" />
            <el-table-column prop="rag_count" label="片库条数" width="92" />
            <el-table-column prop="peer_count" label="他人收藏" width="92" />
            <el-table-column prop="final_count" label="最终推荐" width="100" />
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="danger" @click="deleteRecommendLog(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="👁 浏览记录" name="browse">
          <div class="action-bar">
            <el-input-number v-model="histUserId" :min="1" placeholder="按用户ID筛选" />
            <el-button type="primary" :icon="Refresh" @click="loadBrowseHistory">查询</el-button>
          </div>
          <el-table :data="browseHistory" class="admin-table admin-table--fill" style="width: 100%; margin-top: 20px">
            <el-table-column prop="user_id" label="用户ID" width="90" />
            <el-table-column prop="username" label="用户" min-width="120" show-overflow-tooltip />
            <el-table-column prop="movie_name" label="电影" min-width="160" show-overflow-tooltip />
            <el-table-column prop="view_count" label="次数" width="72" align="center" />
            <el-table-column prop="viewed_at" label="最近查看" width="172" />
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="danger" @click="deleteBrowseRow(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

      </el-tabs>
    </el-card>

    <!-- 编辑用户对话框 -->
    <el-dialog v-model="createUserVisible" class="adm-dlg" title="新建用户" width="420px" align-center>
      <el-form :model="createForm" label-width="88px">
        <el-form-item label="用户名">
          <el-input v-model="createForm.username" autocomplete="off" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="createForm.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option label="user" value="user" />
            <el-option label="admin" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createUserVisible = false">取消</el-button>
        <el-button type="primary" @click="saveCreateUser">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editUserVisible" class="adm-dlg" title="编辑用户" width="400px" align-center>
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="用户名">
          <el-input v-model="editForm.username" disabled />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input
            v-model="editForm.newPassword"
            type="password"
            placeholder="留空表示不修改"
          />
        </el-form-item>
        <el-form-item label="新角色">
          <el-select v-model="editForm.newRole" style="width: 100%">
            <el-option label="user" value="user" />
            <el-option label="admin" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editUserVisible = false">取消</el-button>
        <el-button type="primary" @click="saveUserEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { adminApi } from '@/services/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import type { ModelLog } from '@/types'

const activeTab = ref('stats')

/** 展示用时间（兼容仍带 ISO ``T`` 或小数秒的字符串） */
const formatDbDateTime = (v: unknown): string => {
  if (v == null) return ''
  let s = String(v).trim().replace('T', ' ')
  if (!s) return ''
  if (s.endsWith('Z')) s = s.slice(0, -1).trim()
  const dot = s.indexOf('.')
  if (dot > 0 && s[4] === '-' && s[7] === '-') s = s.slice(0, dot)
  const plus = s.indexOf('+')
  if (plus > 0 && s[4] === '-' && s[7] === '-') s = s.slice(0, plus).trim()
  return s.length >= 19 ? s.slice(0, 19) : s
}

const createUserVisible = ref(false)
const createForm = ref({ username: '', password: '', role: 'user' })

const openCreateUser = () => {
  createForm.value = { username: '', password: '', role: 'user' }
  createUserVisible.value = true
}

const saveCreateUser = async () => {
  if (!createForm.value.username.trim() || !createForm.value.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  try {
    await adminApi.createUser(
      createForm.value.username.trim(),
      createForm.value.password,
      createForm.value.role
    )
    ElMessage.success('用户已创建')
    createUserVisible.value = false
    loadUsers()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '创建失败')
  }
}

// 用户管理
const users = ref<any[]>([])
const loadUsers = async () => {
  try {
    const response = await adminApi.getUsers()
    users.value = (response.data.users || []).map((u: any) => ({
      ...u,
      created_at: formatDbDateTime(u.created_at),
      review_muted_until: formatDbDateTime(u.review_muted_until)
    }))
  } catch (error: any) {
    ElMessage.error('加载用户列表失败')
    console.error(error)
  }
}

// 编辑用户
const editUserVisible = ref(false)
const editForm = ref({
  userId: 0,
  username: '',
  newPassword: '',
  newRole: 'user',
  originalRole: 'user'
})

const showEditUserDialog = (user: any) => {
  editForm.value = {
    userId: user.id,
    username: user.username,
    newPassword: '',
    newRole: user.role,
    originalRole: user.role
  }
  editUserVisible.value = true
}

const saveUserEdit = async () => {
  try {
    if (editForm.value.newPassword) {
      await adminApi.updateUserPassword(editForm.value.userId, editForm.value.newPassword)
      ElMessage.success('密码已修改')
    }
    if (editForm.value.newRole !== editForm.value.originalRole) {
      await adminApi.updateUserRole(editForm.value.userId, editForm.value.newRole)
      ElMessage.success('角色已修改')
    }
    editUserVisible.value = false
    loadUsers()
  } catch (error: any) {
    ElMessage.error('保存失败')
    console.error(error)
  }
}

const deleteUser = async (userId: number) => {
  try {
    await ElMessageBox.confirm('确定删除该用户吗？', '警告', {
      type: 'warning'
    })
    await adminApi.deleteUser(userId)
    ElMessage.success('用户已删除')
    loadUsers()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// 收藏管理
const favUsername = ref('')
const favorites = ref<any[]>([])
const loadFavorites = async () => {
  try {
    const u = favUsername.value.trim()
    const response = await adminApi.getAllFavorites(undefined, u || undefined)
    const rows = (response.data.favorites || []) as any[]
    favorites.value = rows.map((r) => ({
      ...r,
      added_at: formatDbDateTime(r.added_at)
    }))
  } catch (error: any) {
    ElMessage.error('加载收藏列表失败')
    console.error(error)
  }
}

const deleteFavorite = async (favId: number) => {
  try {
    await ElMessageBox.confirm('确定删除该收藏记录吗？', '提示', {
      type: 'warning'
    })
    await adminApi.deleteFavoriteAdmin(favId)
    ElMessage.success('收藏已删除')
    loadFavorites()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

// 推荐日志
const recommendLogs = ref<any[]>([])
const loadRecommendLogs = async () => {
  try {
    const response = await adminApi.getRecommendLogs()
    recommendLogs.value = (response.data.logs || []).map((r: any) => {
      const inf =
        r.inference_meta && typeof r.inference_meta === 'object' ? r.inference_meta : null
      const peerArr = Array.isArray(inf?.peer_fav_movies) ? inf.peer_fav_movies : []
      return {
        ...r,
        created_at: formatDbDateTime(r.created_at),
        kg_count: Array.isArray(r.kg_movies) ? r.kg_movies.length : 0,
        rag_count: Array.isArray(r.rag_movies) ? r.rag_movies.length : 0,
        peer_count: peerArr.length,
        final_count: Array.isArray(r.final_movies) ? r.final_movies.length : 0,
        inference_meta: inf
      }
    })
  } catch (error: any) {
    ElMessage.error('加载推荐日志失败')
    console.error(error)
  }
}

const deleteRecommendLog = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定删除该条推荐日志吗？', '提示', { type: 'warning' })
    await adminApi.deleteRecommendLog(id)
    ElMessage.success('已删除')
    loadRecommendLogs()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

const displayTitle = (t: string) => (t || '').replace(/_/g, ' ')

const _normTitle = (t: string) =>
  String(t || '')
    .trim()
    .toLowerCase()
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')

const isFinalPicked = (row: any, title: string) => {
  const finals = Array.isArray(row?.final_movies) ? row.final_movies : []
  const s = new Set(finals.map((x: any) => _normTitle(String(x || ''))).filter(Boolean))
  return s.has(_normTitle(title))
}

const peerFavCandidates = (row: any) => {
  const arr = row?.inference_meta?.peer_fav_movies
  return Array.isArray(arr) ? arr : []
}
const peerFavTitle = (m: any) => {
  if (m == null) return ''
  if (typeof m === 'string') return String(m).trim()
  return String(m.display || m.name || '').trim()
}
const peerFavKey = (m: any, idx: number) => `${peerFavTitle(m)}-${idx}`

const pipelineStatusTagType = (s: string | undefined) => {
  const x = (s || '').toLowerCase()
  if (x === 'ok') return 'success'
  if (x === 'warn') return 'warning'
  if (x === 'skip') return 'info'
  if (x === 'error') return 'danger'
  return 'info'
}

const formatStepMs = (ms: number) => {
  const n = Number(ms)
  if (!Number.isFinite(n)) return '—'
  if (n >= 1000) return `${(n / 1000).toFixed(2)} s`
  return `${Math.round(n)} ms`
}

const hasKgMeta = (inf: Record<string, unknown> | null | undefined) => {
  if (!inf || typeof inf !== 'object') return false
  const m = inf.kg_model_meta as Record<string, unknown> | undefined
  if (!m || typeof m !== 'object') return false
  const ru = m.relations_used
  return !!(
    m.method ||
    m.note ||
    (Array.isArray(ru) && ru.length) ||
    m.genre_boost != null
  )
}

const prefDecomposeSummary = (p: Record<string, unknown> | null | undefined) => {
  if (!p || typeof p !== 'object') return ''
  const bits: string[] = []
  const q = p.query
  if (q && String(q).trim()) bits.push(`检索式：${String(q).slice(0, 160)}`)
  const lg = p.liked_genres
  if (Array.isArray(lg) && lg.length) bits.push(`偏好类型：${lg.slice(0, 8).join('、')}`)
  const lm = p.liked_movies
  if (Array.isArray(lm) && lm.length) bits.push(`提及片目：${lm.slice(0, 6).join('、')}`)
  const rel = p.relations
  if (Array.isArray(rel) && rel.length) bits.push(`关系：${rel.slice(0, 8).join('、')}`)
  return bits.join(' · ')
}

// 系统概览（产品化）
const overview = ref<any>({
  counts: { users: 0, favorites: 0, watched: 0, browse_history: 0, recommend_logs: 0 },
  runtime: {
    tmdb_configured: false,
    poster_cache_enabled: false,
    poster_cache_root: '',
    kg_loaded: false,
    rag_loaded: false
  },
  system: {
    douban_movie_count: 0,
    tmdb_csv_movie_count: 0,
    rag_document_count: 0,
    tmdb_home_last_refresh_display: '',
    tmdb_home_note: ''
  }
})

const onRefreshStatsTab = async () => {
  await Promise.all([loadOverview(), loadModelStats(), loadKgEvalDisplay()])
}

const loadOverview = async () => {
  try {
    const { data } = await adminApi.getOverview()
    const d = data as Record<string, unknown> | undefined
    if (d && typeof d === 'object') {
      overview.value = {
        ...overview.value,
        counts: { ...overview.value.counts, ...((d.counts as object) || {}) },
        runtime: { ...overview.value.runtime, ...((d.runtime as object) || {}) },
        system: { ...overview.value.system, ...((d.system as object) || {}) }
      }
    }
  } catch (e: any) {
    ElMessage.error('加载概览失败')
    console.error(e)
  }
}

const histUserId = ref<number | null>(null)
const browseHistory = ref<any[]>([])
const loadBrowseHistory = async () => {
  try {
    const response = await adminApi.getBrowseHistory(200, histUserId.value || undefined)
    const rows = (response.data.history || []) as any[]
    browseHistory.value = rows.map((r) => ({
      ...r,
      viewed_at: formatDbDateTime(r.viewed_at)
    }))
  } catch (e: any) {
    ElMessage.error('加载浏览记录失败')
    console.error(e)
  }
}

const deleteBrowseRow = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定删除该条浏览记录？', '提示', { type: 'warning' })
    await adminApi.deleteBrowseHistoryRecord(id)
    ElMessage.success('已删除')
    loadBrowseHistory()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// 模型统计
const modelStats = ref<ModelLog[]>([])
const modelLogs = ref<any[]>([])
const modelStatsView = computed(() =>
  (modelStats.value || []).map((r: any) => ({
    ...r,
    avg_s: (Number(r.avg_ms || 0) / 1000).toFixed(1)
  }))
)
const modelLogsView = computed(() =>
  (modelLogs.value || []).map((r: any) => ({
    ...r,
    created_at: formatDbDateTime(r.created_at),
    elapsed_s: (Number(r.elapsed_ms || 0) / 1000).toFixed(1)
  }))
)
const loadModelStats = async () => {
  try {
    const response = await adminApi.getModelStats()
    modelStats.value = response.data.stats
    modelLogs.value = response.data.recent_logs
  } catch (error: any) {
    ElMessage.error('加载统计失败')
    console.error(error)
  }
}

/** 模型评估展示 JSON（backend/data/eval/kg_eval_display.json） */
const kgEvalConfigured = ref(false)
const kgEvalMessage = ref('')
const kgEvalPayload = ref<Record<string, unknown> | null>(null)

const kgEvalMetricsOrder = ['Hits@1', 'Hits@3']

function formatKgScalarLabel(key: string, val: unknown): string {
  const n = Number(val)
  if (Number.isNaN(n)) return String(val ?? '')
  if (key === 'MRR' || key === 'MR') return n.toFixed(4)
  if (key.startsWith('Hits@') && n >= 0 && n <= 1) return `${(n * 100).toFixed(2)}%`
  return String(val)
}

const kgEvalMetricsRows = computed(() => {
  const m = kgEvalPayload.value?.metrics as Record<string, unknown> | undefined
  if (!m || typeof m !== 'object') return [] as { k: string; v: string }[]
  const seen = new Set<string>()
  const rows: { k: string; v: string }[] = []
  for (const k of kgEvalMetricsOrder) {
    const v = (m as any)[k]
    if (v === null || v === undefined) continue
    rows.push({ k, v: formatKgScalarLabel(k, v) })
    seen.add(k)
  }
  for (const k of Object.keys(m)) {
    if (seen.has(k)) continue
    const v = (m as any)[k]
    if (v === null || v === undefined) continue
    rows.push({ k, v: formatKgScalarLabel(k, v) })
  }
  return rows
})

const kgEvalBaselines = computed(() => {
  const raw = (kgEvalPayload.value as any)?.baselines
  return Array.isArray(raw) ? (raw as any[]) : ([] as any[])
})

function formatKgMetricCell(val: unknown): string {
  if (val === null || val === undefined) return '—'
  const n = Number(val)
  if (Number.isNaN(n)) return '—'
  if (n >= 0 && n <= 1) return `${(n * 100).toFixed(2)}%`
  return `${n.toFixed(2)}%`
}

const loadKgEvalDisplay = async () => {
  try {
    const { data } = await adminApi.getKgEvalDisplay()
    const d = data as Record<string, unknown>
    kgEvalConfigured.value = !!d?.configured
    kgEvalMessage.value = typeof d?.message === 'string' ? d.message : ''
    kgEvalPayload.value = (d?.payload as Record<string, unknown>) || null
  } catch (e: any) {
    kgEvalConfigured.value = false
    kgEvalMessage.value = e.response?.data?.detail || '加载模型评估配置失败'
    kgEvalPayload.value = null
  }
}

const kgBaselineRowClass = ({ row }: { row: Record<string, unknown> }) =>
  row.highlight ? 'kg-baseline-row--hi' : ''

const openMute = async (userId: number) => {
  try {
    const { value } = await ElMessageBox.prompt('禁言时长（小时）。例如 24/168/720；输入 0 视为取消。', '影评禁言', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputValue: '24',
      inputValidator: (v) => {
        const n = Number(v)
        if (Number.isNaN(n) || n < 0) return '请输入>=0的数字'
        return true
      }
    })
    const hours = Number(value)
    if (hours === 0) {
      await adminApi.unmuteUserReviews(userId)
      ElMessage.success('已取消禁言')
    } else {
      await adminApi.muteUserReviews(userId, { duration_hours: hours, reason: '' })
      ElMessage.success('已禁言')
    }
    loadUsers()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

onMounted(() => {
  loadUsers()
  loadFavorites()
  loadRecommendLogs()
  loadBrowseHistory()
  loadModelStats()
  loadOverview()
  loadKgEvalDisplay()
})

watch(activeTab, (name) => {
  if (name === 'stats') {
    loadOverview()
    loadModelStats()
    loadKgEvalDisplay()
  } else if (name === 'logs') {
    loadRecommendLogs()
  }
})
</script>

<style scoped>
.admin-container {
  padding: 16px 20px 40px;
  max-width: 1400px;
  margin: 0 auto;
}

.glass-admin {
  border-radius: 20px !important;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  background: rgba(255, 255, 255, 0.06) !important;
  backdrop-filter: blur(18px) saturate(1.12);
  box-shadow:
    0 0 0 1px rgba(129, 140, 248, 0.06) inset,
    0 22px 70px rgba(0, 0, 0, 0.28) !important;
  min-height: 620px;
  --el-card-bg-color: transparent;
}

.admin-card :deep(.el-card__header) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding: 16px 20px;
}

.admin-card :deep(.el-card__body) {
  padding: 18px 20px 24px;
}

.card-header {
  font-size: 1.15rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: rgba(248, 250, 252, 0.94);
}

.admin-card :deep(.el-tabs__header) {
  margin-bottom: 8px;
}

.admin-card :deep(.el-tabs__nav-wrap::after) {
  background: rgba(255, 255, 255, 0.1);
}

.admin-card :deep(.el-tabs__item) {
  color: rgba(203, 213, 225, 0.88);
  font-weight: 600;
}

.admin-card :deep(.el-tabs__item.is-active) {
  color: rgba(248, 250, 252, 0.96);
}

.admin-card :deep(.el-tabs__active-bar) {
  height: 3px;
  border-radius: 3px;
  background: linear-gradient(90deg, #6366f1, #a855f7);
}

.admin-card :deep(.el-table) {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: rgba(2, 6, 23, 0.28);
  --el-table-header-bg-color: rgba(15, 23, 42, 0.75);
  --el-table-row-hover-bg-color: rgba(99, 102, 241, 0.14);
  --el-table-text-color: rgba(226, 232, 240, 0.92);
  --el-table-header-text-color: rgba(248, 250, 252, 0.88);
  --el-table-border-color: rgba(255, 255, 255, 0.08);
}

.action-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.admin-card :deep(.el-input__wrapper),
.admin-card :deep(.el-input-number .el-input__wrapper) {
  background: rgba(2, 6, 23, 0.38);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
}

.admin-card :deep(.el-input__inner) {
  color: rgba(248, 250, 252, 0.94);
}

.admin-card :deep(.el-tabs__content) {
  color: rgba(226, 232, 240, 0.92);
  background: transparent;
}

.admin-card :deep(.el-tabs__nav-scroll),
.admin-card :deep(.el-tabs__nav-wrap) {
  background: transparent;
}

.admin-card :deep(.el-select .el-input__wrapper),
.admin-card :deep(.el-select__wrapper) {
  background: rgba(2, 6, 23, 0.38) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
}

.admin-card :deep(.el-select .el-input__inner),
.admin-card :deep(.el-select__selected-item) {
  color: rgba(248, 250, 252, 0.94);
}

/* 系统概览内层卡片：与主卡同系深色玻璃 */
.nested-glass {
  border-radius: 16px !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  background: rgba(2, 6, 23, 0.42) !important;
  --el-card-bg-color: transparent;
  backdrop-filter: blur(14px) saturate(1.08);
  box-shadow: 0 0 0 1px rgba(129, 140, 248, 0.05) inset, 0 14px 40px rgba(0, 0, 0, 0.22) !important;
}

.recent-logs-scroll {
  max-height: 360px;
  overflow: auto;
  padding-right: 4px; /* 给滚动条留出一点空间 */
}

/* 仅滚动容器内的表格头部保持可见（Element Plus） */
.recent-logs-scroll :deep(.el-table__header-wrapper) {
  position: sticky;
  top: 0;
  z-index: 2;
}

.nested-glass :deep(.el-card__header) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding: 12px 16px;
  color: rgba(248, 250, 252, 0.92);
  font-weight: 650;
}

.nested-glass :deep(.el-card__body) {
  padding: 8px 12px 14px;
  background: transparent !important;
}

.kg-eval-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.kg-eval-title {
  font-size: 1.05rem;
  font-weight: 750;
  color: rgba(248, 250, 252, 0.95);
  margin: 4px 0 8px;
}

.kg-eval-meta {
  margin: 0 0 6px;
  font-size: 13px;
  color: rgba(203, 213, 225, 0.9);
  line-height: 1.45;
}

.kg-eval-meta.muted {
  color: rgba(148, 163, 184, 0.88);
  font-size: 12px;
}

.kg-eval-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 12px 0 14px;
}

.kg-eval-metric {
  min-width: 120px;
  flex: 1 1 120px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(129, 140, 248, 0.25);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.18), rgba(30, 27, 75, 0.35));
}

.kg-eval-mk {
  font-size: 11px;
  font-weight: 600;
  color: rgba(199, 210, 254, 0.85);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.kg-eval-mv {
  margin-top: 6px;
  font-size: 1.35rem;
  font-weight: 800;
  color: rgba(248, 250, 252, 0.96);
  font-variant-numeric: tabular-nums;
}

.kg-eval-subh {
  font-size: 13px;
  font-weight: 650;
  color: rgba(226, 232, 240, 0.9);
  margin: 14px 0 8px;
}

.kg-baseline-table :deep(tr.kg-baseline-row--hi) {
  background: rgba(99, 102, 241, 0.12) !important;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

@media (max-width: 1100px) {
  .overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.overview-grid--sys {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

@media (max-width: 1100px) {
  .overview-grid--sys {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.ov-tmdb-home {
  width: 100%;
  box-sizing: border-box;
}

.ov-line {
  font-size: 1.05rem;
  font-weight: 750;
  line-height: 1.35;
  color: rgba(248, 250, 252, 0.94);
  margin-top: 4px;
  font-variant-numeric: tabular-nums;
}

.admin-table--fill :deep(.el-table__inner-wrapper) {
  width: 100%;
}

.admin-table--fill :deep(table) {
  width: 100% !important;
}

.admin-card :deep(td.el-table__expanded-cell) {
  background: rgba(99, 102, 241, 0.14) !important;
}

.admin-card :deep(td.el-table__expanded-cell .cell) {
  background: transparent !important;
}

.admin-card :deep(.el-table__expanded-cell .el-empty__description) {
  color: rgba(148, 163, 184, 0.95);
}

.admin-card :deep(.el-table__expanded-cell .el-empty) {
  background: transparent !important;
}

/* 收藏管理：均匀留白；勿对 EP 表格用 table-layout:fixed+百分比，易与 fixed 列组合导致内容被挤成省略号 */
.admin-fav-table :deep(.el-table__cell) {
  padding-left: 12px;
  padding-right: 12px;
}

.ov-card {
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(2, 6, 23, 0.35);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  padding: 14px 14px 12px;
}

.ov-card.wide {
  grid-column: span 2;
}

@media (max-width: 1100px) {
  .ov-card.wide {
    grid-column: span 2;
  }
}

.ov-k {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.92);
  margin-bottom: 6px;
}

.ov-v {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  color: rgba(248, 250, 252, 0.96);
  font-variant-numeric: tabular-nums;
}

.ov-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
}

.ov-path {
  font-size: 12px;
  color: rgba(203, 213, 225, 0.88);
}

.log-expand {
  padding: 8px 8px 12px;
  background: transparent;
}

.log-block {
  display: grid;
  grid-template-columns: 92px 1fr;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px dashed rgba(255, 255, 255, 0.08);
}

.log-block:last-child {
  border-bottom: 0;
}

.log-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding-top: 10px;
}

.log-grid--triple {
  grid-template-columns: 1fr 1fr 1fr;
}

@media (max-width: 900px) {
  .log-grid {
    grid-template-columns: 1fr;
  }
}

.log-mini {
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(2, 6, 23, 0.28);
  padding: 10px 12px;
}

.log-k {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.9);
}

.log-v {
  color: rgba(226, 232, 240, 0.92);
  line-height: 1.6;
}

.log-tag {
  margin: 0 8px 8px 0;
}

.log-more {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.92);
}

.log-text {
  white-space: pre-wrap;
}

.log-mono {
  margin-top: 6px;
  font-size: 12px;
  color: rgba(203, 213, 225, 0.88);
}

.inf-snap-none {
  color: rgba(148, 163, 184, 0.65);
  font-size: 13px;
}

.inf-section {
  margin-bottom: 14px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(2, 6, 23, 0.35);
}

.inf-section-title {
  font-size: 13px;
  font-weight: 700;
  color: rgba(248, 250, 252, 0.95);
  margin-bottom: 10px;
  letter-spacing: 0.02em;
}

.inf-pipeline {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.inf-step {
  padding-left: 10px;
  border-left: 3px solid rgba(56, 189, 248, 0.45);
}

.inf-step--llm {
  border-left-color: rgba(251, 191, 36, 0.65);
}

.inf-llm-mark {
  font-weight: 700;
  letter-spacing: 0.06em;
}

.inf-llm-inline {
  display: inline-block;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 700;
  color: rgba(15, 23, 42, 0.95);
  background: linear-gradient(135deg, #fbbf24, #f59e0b);
}

.inf-step-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
}

.inf-step-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(226, 232, 240, 0.96);
}

.inf-step-ms {
  font-size: 12px;
  color: rgba(148, 163, 184, 0.95);
  font-variant-numeric: tabular-nums;
}

.inf-step-msg {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(203, 213, 225, 0.9);
  white-space: pre-wrap;
}

.inf-kg-block .inf-kg-inner {
  font-size: 12px;
  line-height: 1.55;
  color: rgba(226, 232, 240, 0.9);
}

.inf-mono-line {
  margin: 0 0 8px;
  font-size: 12px;
  color: rgba(186, 230, 253, 0.92);
}

.inf-note {
  margin: 0 0 10px;
  white-space: pre-wrap;
  color: rgba(203, 213, 225, 0.92);
}

.inf-kv {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-bottom: 8px;
  align-items: baseline;
}

.inf-k {
  flex: 0 0 auto;
  font-size: 12px;
  color: rgba(148, 163, 184, 0.95);
}

.inf-v {
  font-size: 12px;
  color: rgba(226, 232, 240, 0.92);
  word-break: break-word;
}

.inf-seeds {
  flex: 1;
  min-width: 0;
}

.inf-rw-wrap {
  margin-top: 6px;
}

.inf-rw-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin-top: 6px;
}

.inf-rw-item {
  font-size: 11px;
  color: rgba(203, 213, 225, 0.88);
}

.inf-rw-item code {
  font-size: 11px;
  color: rgba(125, 211, 252, 0.95);
  margin-right: 4px;
}

.inf-flow-sum {
  margin: 10px 0 0;
  font-size: 11px;
  line-height: 1.5;
  color: rgba(148, 163, 184, 0.9);
}

.inf-pref-preview {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: rgba(203, 213, 225, 0.9);
}

.inf-llm-table {
  margin-top: 4px;
  --el-table-border-color: rgba(255, 255, 255, 0.08);
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: rgba(2, 6, 23, 0.25);
  --el-table-header-bg-color: rgba(15, 23, 42, 0.65);
}
</style>

<!-- 弹窗挂到 body，须单独非 scoped -->
<style>
.adm-dlg.el-dialog {
  --el-dialog-bg-color: transparent;
  border-radius: 18px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: linear-gradient(165deg, rgba(30, 41, 59, 0.96), rgba(15, 23, 42, 0.99)) !important;
  box-shadow: 0 28px 90px rgba(0, 0, 0, 0.5) !important;
}

.adm-dlg .el-dialog__header {
  padding: 16px 20px 12px;
  margin: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.adm-dlg .el-dialog__title {
  color: rgba(248, 250, 252, 0.96);
  font-weight: 700;
}

.adm-dlg .el-dialog__headerbtn .el-dialog__close {
  color: rgba(203, 213, 225, 0.9);
}

.adm-dlg .el-dialog__body {
  padding: 18px 20px 8px;
  color: rgba(226, 232, 240, 0.92);
  background: transparent;
}

.adm-dlg .el-dialog__footer {
  padding: 12px 20px 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  background: transparent;
}

.adm-dlg .el-form-item__label {
  color: rgba(226, 232, 240, 0.88) !important;
}

.adm-dlg .el-input__wrapper,
.adm-dlg .el-select__wrapper {
  background: rgba(2, 6, 23, 0.45) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
}

.adm-dlg .el-input__inner,
.adm-dlg .el-select__selected-item {
  color: rgba(248, 250, 252, 0.95) !important;
}

.adm-dlg .el-select__placeholder {
  color: rgba(148, 163, 184, 0.85);
}
</style>
