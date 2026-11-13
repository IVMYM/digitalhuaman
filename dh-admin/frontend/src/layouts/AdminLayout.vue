<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Odometer,
  User,
  Cpu,
  Microphone,
  Avatar,
  Collection,
  ChatDotRound,
  Setting,
} from "@element-plus/icons-vue";
import { clearSession, getUsername } from "../api";

const route = useRoute();
const router = useRouter();
const username = computed(() => getUsername() || "管理员");
const title = computed(() => route.meta.title || "概览");

const items = [
  { to: "/", label: "概览", icon: Odometer },
  { to: "/avatars", label: "形象管理", icon: User },
  { to: "/brains", label: "大脑管理", icon: Cpu },
  { to: "/voices", label: "声音管理", icon: Microphone },
  { to: "/personas", label: "数字人角色", icon: Avatar },
  { to: "/knowledge", label: "知识库", icon: Collection },
  { to: "/chat", label: "对话测试", icon: ChatDotRound },
  { to: "/settings", label: "设置", icon: Setting },
];

function logout() {
  clearSession();
  router.push({ name: "login" });
}

function isActive(path) {
  if (path === "/") return route.path === "/";
  return route.path === path || route.path.startsWith(`${path}/`);
}
</script>

<template>
  <div class="shell">
    <aside class="side">
      <div class="brand">
        <strong>征信数字人管理后台</strong>
      </div>
      <nav>
        <router-link
          v-for="item in items"
          :key="item.to"
          :to="item.to"
          active-class="unused"
          exact-active-class="unused"
          :class="{ 'nav-on': isActive(item.to) }"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          {{ item.label }}
        </router-link>
      </nav>
    </aside>
    <div class="main">
      <header class="top">
        <h1>{{ title }}</h1>
        <div class="who">
          <span>{{ username }}</span>
          <el-button text @click="logout">退出</el-button>
        </div>
      </header>
      <section class="content">
        <router-view />
      </section>
    </div>
  </div>
</template>
