<template>
  <el-dialog
    :model-value="modelValue"
    title="推荐快照"
    width="min(920px, 96vw)"
    class="rec-snap-dlg"
    destroy-on-close
    append-to-body
    align-center
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <RecommendSnapshotBody :payload="payload" />
    <template #footer>
      <el-button round @click="$emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import RecommendSnapshotBody from './RecommendSnapshotBody.vue'
import type { RecommendSnapshotPayload } from './RecommendSnapshotBody.vue'

defineProps<{
  modelValue: boolean
  payload: RecommendSnapshotPayload | null
}>()

defineEmits<{
  'update:modelValue': [v: boolean]
}>()
</script>

<script lang="ts">
export type { RecommendSnapshotPayload, SnapMovie } from './RecommendSnapshotBody.vue'
</script>

<style>
.rec-snap-dlg.el-dialog {
  --el-dialog-bg-color: rgba(15, 23, 42, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
}
.rec-snap-dlg .el-dialog__header {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  margin-right: 0;
  padding-bottom: 12px;
}
.rec-snap-dlg .el-dialog__title {
  color: rgba(248, 250, 252, 0.96);
  font-weight: 700;
}
.rec-snap-dlg .el-dialog__body {
  padding-top: 12px;
  color: rgba(226, 232, 240, 0.92);
}
</style>
