<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";
import { formatBytes, formatUptime } from "../options";
import RestartDigitalHuman from "../components/RestartDigitalHuman.vue";

const loading = ref(true);
const data = ref(null);

const cards = [
  { key: "avatars", label: "形象", to: "/avatars" },
  { key: "brains", label: "大脑", to: "/brains" },
  { key: "voices", label: "声音", to: "/voices" },
  { key: "personas", label: "角色", to: "/personas", extra: "personas_enabled" },
  { key: "knowledge_bases", label: "知识库", to: "/knowledge" },
  { key: "documents", label: "文档", to: "/knowledge" },
];

onMounted(async () => {
  try {
    data.value = await api("/api/dashboard");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div v-loading="loading">
    <div class="stats">
      <router-link v-for="card in cards" :key="card.key" :to="card.to" class="panel stat">
        <span>{{ card.label }}</span>
        <b>{{ data?.counts?.[card.key] ?? "—" }}</b>
        <em v-if="card.extra">其中 {{ data?.counts?.[card.extra] ?? 0 }} 个启用</em>
      </router-link>
    </div>
    <div class="grid-2">
      <article class="panel">
        <div class="panel-bar">
          <div>
            <h2>系统状态</h2>
            <p>这台机器只跑管理后台。SQLite 和上传文件都在数据目录里。</p>
          </div>
          <RestartDigitalHuman />
        </div>
        <dl v-if="data" class="status">
          <div>
            <dt>数据库</dt>
            <dd><i class="dot" />{{ data.status.database_scheme === "sqlite" ? "SQLite" : data.status.database_scheme }}，连接正常</dd>
          </div>
          <div>
            <dt>数据目录</dt>
            <dd>{{ data.status.data_dir_writable ? "可写" : "不可写" }} · {{ formatBytes(data.status.data_dir_bytes) }}</dd>
          </div>
          <div>
            <dt>磁盘剩余</dt>
            <dd>{{ formatBytes(data.status.disk_free_bytes) }} / {{ formatBytes(data.status.disk_total_bytes) }}</dd>
          </div>
          <div>
            <dt>运行时令牌</dt>
            <dd>
              <i class="dot" :class="{ off: !data.status.runtime_token_configured }" />
              {{ data.status.runtime_token_configured ? "已配置" : "未配置" }}
            </dd>
          </div>
          <div>
            <dt>LiveTalking</dt>
            <dd><i class="dot" :class="{ off: !data.status.livetalking?.online }" />{{ data.status.livetalking?.online ? "在线" : "离线" }} · {{ data.status.livetalking?.sessions ?? 0 }} / {{ data.status.livetalking?.max_session ?? "—" }} 会话</dd>
          </div>
          <div>
            <dt>默认形象</dt>
            <dd>{{ data.status.default_avatar || "未设置" }}</dd>
          </div>
          <div>
            <dt>默认角色</dt>
            <dd>{{ data.status.default_persona || "未设置" }}</dd>
          </div>
          <div>
            <dt>已运行</dt>
            <dd>{{ formatUptime(data.status.uptime_seconds) }} · v{{ data.status.version }}</dd>
          </div>
        </dl>
      </article>
      <article class="panel">
        <div class="panel-bar">
          <div>
            <h2>{{ data?.counts?.personas ? "接下来" : "先配一个角色" }}</h2>
            <p>GPU 还没接上时，也可以在对话测试里确认大脑和人设。</p>
          </div>
        </div>
        <ol class="checklist">
          <li>在形象管理里登记 LiveTalking 的 avatar_id，可上传预览图和源视频。</li>
          <li>在大脑管理里填写 OpenAI 兼容接口，用「测试连接」看回复和耗时。</li>
          <li>在声音管理里选择 TTS 引擎、音色和参考音频。</li>
          <li>把三者合成一个数字人角色，需要的话挂上知识库。</li>
          <li>到对话测试发一句话。LiveTalking 以后把 LLM 地址指到本服务的 /v1。</li>
        </ol>
      </article>
    </div>
  </div>
</template>
