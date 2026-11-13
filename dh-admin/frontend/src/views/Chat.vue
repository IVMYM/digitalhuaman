<script setup>
import { computed, nextTick, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { api, getToken } from "../api";

const personas = ref([]);
const personaId = ref(null);
const input = ref("");
const messages = ref([]);
const sending = ref(false);
const latency = ref(null);
const box = ref(null);
const current = computed(() => personas.value.find((item) => item.id === personaId.value) || null);

async function load() {
  try {
    personas.value = await api("/api/personas");
    const preferred = personas.value.find((item) => item.enabled && item.is_default) || personas.value.find((item) => item.enabled) || personas.value[0];
    if (preferred) personaId.value = preferred.id;
  } catch (error) {
    ElMessage.error(error.message);
  }
}

function reset() {
  messages.value = [];
  latency.value = null;
}

async function scrollDown() {
  await nextTick();
  if (box.value) box.value.scrollTop = box.value.scrollHeight;
}

async function send() {
  const text = input.value.trim();
  if (!text || !personaId.value || sending.value) return;
  input.value = "";
  messages.value.push({ role: "user", content: text });
  const assistant = { role: "assistant", content: "", error: "" };
  messages.value.push(assistant);
  sending.value = true;
  latency.value = null;
  await scrollDown();
  const history = messages.value
    .slice(0, -1)
    .filter((item) => item.content)
    .map((item) => ({ role: item.role, content: item.content }));
  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({ persona_id: personaId.value, messages: history }),
    });
    if (response.status === 401) {
      location.assign("/login");
      return;
    }
    if (!response.ok || !response.body) {
      const raw = await response.text();
      let message = raw;
      try {
        message = JSON.parse(raw).detail || raw;
      } catch {
        message = raw;
      }
      assistant.error = typeof message === "string" ? message : "请求失败";
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const line = part.split("\n").find((item) => item.startsWith("data:"));
        if (!line) continue;
        let payload;
        try {
          payload = JSON.parse(line.slice(5).trim());
        } catch {
          continue;
        }
        if (payload.delta) {
          assistant.content += payload.delta;
          await scrollDown();
        }
        if (payload.error) assistant.error = payload.error;
        if (payload.done) latency.value = payload.latency_ms;
      }
    }
  } catch (error) {
    assistant.error = error.message || "连接中断";
  } finally {
    sending.value = false;
    await scrollDown();
  }
}

function onKeydown(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    send();
  }
}

onMounted(load);
</script>

<template>
  <div class="chat-wrap">
    <aside class="panel chat-side">
      <h2>选择角色</h2>
      <el-select v-model="personaId" placeholder="还没有角色" style="width: 100%" @change="reset">
        <el-option v-for="item in personas" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <div v-if="current" class="meta" style="margin-top: 14px">
        <div>形象：{{ current.avatar_name }}</div>
        <div>大脑：{{ current.brain_name }}</div>
        <div>声音：{{ current.voice_name }}</div>
        <div>知识库：{{ current.knowledge_base_name || "未挂" }}</div>
        <div style="margin-top: 8px">
          <el-tag v-if="current.enabled" type="success">启用</el-tag>
          <el-tag v-else type="info">已停用</el-tag>
          <el-tag v-if="current.is_default" type="warning" style="margin-left: 6px">默认</el-tag>
        </div>
        <p>{{ current.description || "这里只调用大脑，不驱动口型。用来在没有 GPU 时确认人设和接口。" }}</p>
      </div>
      <el-empty v-else description="先到「数字人角色」里组合一个" />
    </aside>
    <section class="panel chat-main">
      <div class="panel-bar" style="padding-left: 0; padding-right: 0">
        <div>
          <h2>对话</h2>
          <p>回复按流式返回。Shift+Enter 换行。</p>
        </div>
        <span v-if="latency != null" class="meta">耗时 {{ latency }} ms</span>
      </div>
      <div ref="box" class="transcript">
        <div v-if="!messages.length" class="meta">选好角色后发一句，例如「用一句话介绍你自己」。</div>
        <div
          v-for="(item, index) in messages"
          :key="index"
          class="bubble"
          :class="[item.role, { error: item.error, pending: sending && item.role === 'assistant' && index === messages.length - 1 && !item.content && !item.error }]"
        >
          <template v-if="item.error">{{ item.error }}</template>
          <template v-else>{{ item.content || (item.role === "assistant" && sending ? "" : "") }}</template>
        </div>
      </div>
      <div class="composer">
        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          resize="none"
          placeholder="输入想对数字人说的话"
          @keydown="onKeydown"
        />
        <el-button type="primary" :disabled="!personaId || sending" :loading="sending" @click="send">发送</el-button>
      </div>
    </section>
  </div>
</template>
