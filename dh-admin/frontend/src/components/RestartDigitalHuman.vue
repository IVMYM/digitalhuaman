<script setup>
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api";

const visible = ref(false);
const running = ref(false);
const target = ref("dsw");
const host = ref("");
const result = ref(null);

async function open() {
  result.value = null;
  visible.value = true;
  try {
    const data = await api("/api/system/settings");
    host.value = data.dsw_host || "";
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function run() {
  running.value = true;
  result.value = null;
  try {
    result.value = await api("/api/system/restart-display", {
      method: "POST",
      json: { dsw_host: host.value, target: target.value },
    });
    if (result.value.ok) ElMessage.success("数字人已重启，新配置生效");
    else ElMessage.warning("重启没有完全成功，看下面步骤");
  } catch (error) {
    result.value = { ok: false, steps: [{ name: "请求管理端", ok: false, detail: error.message }] };
  } finally {
    running.value = false;
  }
}
</script>

<template>
  <el-button type="warning" plain @click="open">重启数字人</el-button>
  <el-dialog v-model="visible" title="重启数字人（展示端 8000）" width="600px">
    <el-form label-position="top">
      <el-form-item label="重启目标">
        <el-radio-group v-model="target">
          <el-radio value="dsw">DSW</el-radio>
          <el-radio value="local">本机 localhost</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="target === 'dsw'" label="DSW 主机名">
        <el-input v-model="host" placeholder="colab-livetalking-1.YOUR-HOST.ts.net" />
      </el-form-item>
    </el-form>
    <p class="hint">
      点「推送并重启」后：把默认角色绑定的大脑配置（DSH 专家或 OpenAI 兼容接口）写入目标展示端的
      .env，然后只重启 8000 展示端进程，引擎（8010）不动。整个过程约半分钟，期间页面会短暂断开。
    </p>
    <div v-if="result" class="test-box">
      <div v-for="(step, index) in result.steps" :key="index" style="margin: 4px 0">
        <span :style="{ color: step.ok ? '#67c23a' : '#f56c6c' }">{{ step.ok ? "✔" : "✘" }}</span>
        {{ step.name }}<span v-if="step.detail"> · {{ step.detail }}</span>
      </div>
      <el-alert
        v-if="result.ok"
        type="success"
        :closable="false"
        style="margin-top: 10px"
        title="重启完成"
        description="刷新数字人页面即可，新大脑配置已生效。"
      />
    </div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" :loading="running" @click="run">推送并重启</el-button>
    </template>
  </el-dialog>
</template>
