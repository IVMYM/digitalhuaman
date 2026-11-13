import { createRouter, createWebHistory } from "vue-router";
import { getToken } from "../api";
import AdminLayout from "../layouts/AdminLayout.vue";
import Login from "../views/Login.vue";
import Dashboard from "../views/Dashboard.vue";
import Avatars from "../views/Avatars.vue";
import Brains from "../views/Brains.vue";
import Voices from "../views/Voices.vue";
import Personas from "../views/Personas.vue";
import Knowledge from "../views/Knowledge.vue";
import Chat from "../views/Chat.vue";
import Settings from "../views/Settings.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: Login, meta: { public: true, title: "登录" } },
    {
      path: "/",
      component: AdminLayout,
      children: [
        { path: "", name: "dashboard", component: Dashboard, meta: { title: "概览" } },
        { path: "avatars", name: "avatars", component: Avatars, meta: { title: "形象管理" } },
        { path: "brains", name: "brains", component: Brains, meta: { title: "大脑管理" } },
        { path: "voices", name: "voices", component: Voices, meta: { title: "声音管理" } },
        { path: "personas", name: "personas", component: Personas, meta: { title: "数字人角色" } },
        { path: "knowledge", name: "knowledge", component: Knowledge, meta: { title: "知识库" } },
        { path: "chat", name: "chat", component: Chat, meta: { title: "对话测试" } },
        { path: "settings", name: "settings", component: Settings, meta: { title: "设置" } },
      ],
    },
  ],
});

router.beforeEach((to) => {
  const token = getToken();
  if (!to.meta.public && !token) return { name: "login", query: { redirect: to.fullPath } };
  if (to.name === "login" && token) return { name: "dashboard" };
  const title = to.meta.title || "数字人管理后台";
  document.title = `${title} · 数字人管理后台`;
  return true;
});

export default router;
