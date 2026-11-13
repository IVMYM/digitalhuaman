<script setup>
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api, setSession } from "../api";

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const form = reactive({ username: "", password: "" });

async function submit() {
  if (!form.username.trim() || !form.password) {
    ElMessage.warning("请填写用户名和密码");
    return;
  }
  loading.value = true;
  try {
    const data = await api("/api/auth/login", { method: "POST", json: form });
    setSession(data.access_token, data.username);
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/";
    router.push(redirect || "/");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-screen">
    <section class="login-hero">
      <div>
        <h1>征信数字人管理后台</h1>
      </div>
    </section>
    <section class="login-panel">
      <form class="login-card" @submit.prevent="submit">
        <h2>登录</h2>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="用户名">
            <el-input v-model="form.username" autocomplete="username" size="large" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="form.password" type="password" show-password autocomplete="current-password" size="large" @keyup.enter="submit" />
          </el-form-item>
          <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="submit">进入后台</el-button>
        </el-form>
      </form>
    </section>
  </div>
</template>
