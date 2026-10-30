<script setup>
// 과제가 Vue(Vite) 골격을 줬을 때 쓰는 폼 컴포넌트 뼈대: 입력 → 로딩 → 오류/결과. 외부 UI 라이브러리 없음.
// 판정은 서버(web-api의 rules.py)가 한다. 화면은 입력 검증·상태 표시만.
// 쓰는 법: src/components/에 복사 → App.vue에서 <JudgeForm @judged="onJudged" />
//   개발: vite.config.js에 server: { proxy: { '/api': 'http://localhost:8000' } } → 같은 출처라 CORS 불필요
//   배포: 빌드 결과(dist)를 FastAPI가 정적 파일로 내보내 같은 출처로. 다른 출처면 서버에 CORS_ORIGINS=<화면 주소>
import { computed, ref } from 'vue'

const props = defineProps({ apiBase: { type: String, default: '' } })
const emit = defineEmits(['judged'])

const form = ref({ equipment_id: 'EQ-001', temperature: null, pressure: null })
const state = ref('idle') // idle | loading | done | error
const result = ref(null)
const error = ref('')
const canSubmit = computed(() => form.value.equipment_id && form.value.temperature !== null && form.value.pressure !== null && state.value !== 'loading')

async function submit() {
  state.value = 'loading'
  error.value = ''
  try {
    const r = await fetch(`${props.apiBase}/api/judgements`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value),
    })
    const data = await r.json()
    if (!r.ok) throw new Error(r.status === 422 ? '입력값 확인: ' + data.detail.map((d) => d.loc.at(-1)).join(', ') : data.detail || String(r.status))
    result.value = data
    state.value = 'done'
    emit('judged', data) // 부모가 목록 갱신 등을 한다(props는 자식에서 바꾸지 않는다)
  } catch (e) {
    error.value = e.message
    state.value = 'error'
  }
}
</script>

<template>
  <form class="judge" @submit.prevent="submit">
    <label>설비 ID <input v-model.trim="form.equipment_id" required maxlength="50" /></label>
    <label>온도(℃) <input v-model.number="form.temperature" type="number" step="any" required min="-50" max="500" /></label>
    <label>압력(bar) <input v-model.number="form.pressure" type="number" step="any" required min="0" max="100" /></label>
    <button :disabled="!canSubmit">{{ state === 'loading' ? '판정 중…' : '판정' }}</button>
    <p role="status" aria-live="polite">
      <span v-if="state === 'idle'">값을 넣고 판정을 누르세요.</span>
      <span v-else-if="state === 'error'" class="error">오류: {{ error }}</span>
      <span v-else-if="state === 'done'">
        <strong :class="result.status">{{ result.status }}</strong>
        {{ result.reasons.join(' / ') || '이상 없음' }} (규칙 {{ result.rule_version }})
      </span>
    </p>
  </form>
</template>

<style scoped>
.judge { display: grid; gap: 0.6rem; max-width: 28rem; }
label { display: grid; gap: 0.2rem; font-weight: 600; }
input, button { font: inherit; padding: 0.45rem; }
.OK { color: #1a7f37; } .WARN { color: #9a6700; } .NG, .error { color: #cf222e; }
</style>
