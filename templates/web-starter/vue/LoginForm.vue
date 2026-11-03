<script setup>
// 로그인 폼(아이디 저장 포함). 성공하면 부모에 'done'(사용자 정보)을 보낸다. 스타일은 ui.css 클래스.
import { ref } from "vue";
import { login } from "./useAuth.js";

const emit = defineEmits(["done"]);
const SAVED = "savedUsername";
const username = ref(localStorage.getItem(SAVED) || "");
const password = ref("");
const remember = ref(Boolean(localStorage.getItem(SAVED)));
const error = ref("");
const busy = ref(false);

async function submit() {
  busy.value = true;
  error.value = "";
  try {
    const me = await login(username.value, password.value);
    remember.value ? localStorage.setItem(SAVED, username.value.trim()) : localStorage.removeItem(SAVED); // 아이디만 저장
    emit("done", me);
  } catch (err) {
    error.value = err.message;
    password.value = "";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <form class="auth card" novalidate @submit.prevent="submit">
    <h1>로그인</h1>
    <div v-if="error" class="alert ng" role="alert">{{ error }}</div>
    <div class="field"><label for="u">아이디</label><input id="u" v-model="username" autocomplete="username" required /></div>
    <div class="field"><label for="p">비밀번호</label><input id="p" v-model="password" type="password" autocomplete="current-password" required /></div>
    <label class="check"><input v-model="remember" type="checkbox" /> 아이디 저장</label>
    <button class="btn primary" :disabled="busy || !username || !password">{{ busy ? "로그인하는 중…" : "로그인" }}</button>
    <div class="links"><a href="/forgot.html">비밀번호 찾기</a><a href="/signup.html">회원가입</a></div>
  </form>
</template>
