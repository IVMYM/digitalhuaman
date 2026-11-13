<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
import RestartDigitalHuman from "../components/RestartDigitalHuman.vue";

const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const rows = ref([]);
const presets = ref([]);
const visible = ref(false);
const hint = ref("");
const testResult = ref(null);
const form = reactive(blank());

const experts = ref([]);
const expertsLoading = ref(false);
const isDsh = computed(() => form.preset === "dsh");

const verifyVisible = ref(false);
const verifying = ref(false);
const verifyResult = ref(null);
const verifyCtx = reactive({
  base_url: "",
  app_id: "",
  api_key: "",
  brain_id: null,
  agent_id: "",
  question: "你好，请用一句话介绍你自己。",
});

function blank() {
  return {
    id: null,
    name: "",
    preset: "",
    base_url: "",
    api_key: "",
    model_name: "",
    temperature: 0.7,
    max_tokens: 1024,
    system_prompt: "",
    app_id: "",
    agent_id: "",
    has_api_key: false,
  };
}

async function load() {
  loading.value = true;
  try {
    const [list, presetList] = await Promise.all([api("/api/brains"), api("/api/brains/presets")]);
    rows.value = list;
    presets.value = presetList;
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  Object.assign(form, blank());
  hint.value = "";
  testResult.value = null;
  experts.value = [];
  visible.value = true;
}

function openEdit(row) {
  Object.assign(form, { ...blank(), ...row, api_key: "" });
  hint.value = row.has_api_key ? "已保存密钥。留空表示不修改。" : "";
  testResult.value = null;
  experts.value = [];
  visible.value = true;
}

function applyPreset(preset) {
  form.preset = preset.id;
  form.base_url = preset.base_url;
  form.model_name = preset.model_name;
  if (!form.name) form.name = preset.name;
  hint.value = preset.hint;
}

function expertLabel(id) {
  const hit = experts.value.find((item) => item.agent_id === id);
  return hit ? hit.name : "";
}

async function loadExperts() {
  expertsLoading.value = true;
  try {
    const data = await api("/api/brains/dsh/experts", {
      method: "POST",
      json: {
        base_url: form.base_url,
        app_id: form.app_id,
        api_key: form.api_key || "",
        brain_id: form.id,
      },
    });
    experts.value = data.experts || [];
    if (!experts.value.length) ElMessage.warning("没有查到已授权专家");
    else ElMessage.success(`查到 ${experts.value.length} 个已授权专家`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    expertsLoading.value = false;
  }
}

async function save() {
  if (isDsh.value) {
    if (!form.app_id.trim()) {
      ElMessage.warning("先填 App ID");
      return;
    }
    if (!form.agent_id) {
      ElMessage.warning("先拉取专家列表并选择一个专家");
      return;
    }
    if (!form.id && !form.api_key) {
      ElMessage.warning("先填 App Secret");
      return;
    }
  }
  saving.value = true;
  try {
    const payload = {
      name: form.name,
      preset: form.preset,
      base_url: form.base_url,
      model_name: form.model_name,
      temperature: form.temperature,
      max_tokens: form.max_tokens,
      system_prompt: form.system_prompt,
      app_id: isDsh.value ? form.app_id : "",
      agent_id: isDsh.value ? form.agent_id : "",
    };
    if (isDsh.value) payload.model_name = expertLabel(form.agent_id) || form.agent_id;
    if (form.api_key) payload.api_key = form.api_key;
    const path = form.id ? `/api/brains/${form.id}` : "/api/brains";
    const method = form.id ? "PUT" : "POST";
    await api(path, { method, json: payload });
    ElMessage.success("大脑已保存");
    visible.value = false;
    await load();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function testBrain() {
  testing.value = true;
  testResult.value = null;
  try {
    testResult.value = await api("/api/brains/test", {
      method: "POST",
      json: {
        base_url: form.base_url,
        model_name: form.model_name,
        api_key: form.api_key || "",
        brain_id: form.id,
      },
    });
  } catch (error) {
    testResult.value = { ok: false, error: error.message };
  } finally {
    testing.value = false;
  }
}

function openVerifyFromForm() {
  Object.assign(verifyCtx, {
    base_url: form.base_url,
    app_id: form.app_id,
    api_key: form.api_key || "",
    brain_id: form.id,
    agent_id: form.agent_id,
  });
  verifyResult.value = null;
  verifyVisible.value = true;
}

function openVerifyFromRow(row) {
  Object.assign(verifyCtx, {
    base_url: row.base_url,
    app_id: row.app_id || "",
    api_key: "",
    brain_id: row.id,
    agent_id: row.agent_id || "",
  });
  verifyResult.value = null;
  verifyVisible.value = true;
}

async function runVerify() {
  verifying.value = true;
  verifyResult.value = null;
  try {
    verifyResult.value = await api("/api/brains/dsh/verify", {
      method: "POST",
      json: { ...verifyCtx },
    });
  } catch (error) {
    verifyResult.value = { ok: false, steps: [], error: error.message, reply: "" };
  } finally {
    verifying.value = false;
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`删除大脑「${row.name}」？`, "删除大脑", { type: "warning" });
  try {
    await api(`/api/brains/${row.id}`, { method: "DELETE" });
    ElMessage.success("已删除");
    await load();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

onMounted(load);
</script>

<template>
  <div class="panel table-wrap" v-loading="loading">
    <div class="panel-bar">
      <div>
        <h2>大脑</h2>
        <p>OpenAI 兼容接口，或 DeepSeek Harness 专家大脑。密钥加密后存在本机，列表里只显示掩码。</p>
      </div>
      <div>
        <RestartDigitalHuman />
        <el-button type="primary" @click="openCreate">新建大脑</el-button>
      </div>
    </div>
    <el-table :data="rows">
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column label="类型 / 模型" min-width="180">
        <template #default="{ row }">{{ row.preset === "dsh" ? `DSH 专家 · ${row.model_name}` : row.model_name }}</template>
      </el-table-column>
      <el-table-column prop="base_url" label="接口地址" min-width="220" show-overflow-tooltip />
      <el-table-column label="密钥" min-width="130">
        <template #default="{ row }">{{ row.has_api_key ? row.api_key_masked : "未填写" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.preset === 'dsh'" link type="success" @click="openVerifyFromRow(row)">验证</el-button>
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty><el-empty description="还没有大脑" /></template>
    </el-table>

    <el-dialog v-model="visible" :title="form.id ? '编辑大脑' : '新建大脑'" width="680px">
      <div class="preset-row">
        <el-button v-for="preset in presets" :key="preset.id" @click="applyPreset(preset)">{{ preset.name }}</el-button>
      </div>
      <p v-if="hint" class="hint">{{ hint }}</p>
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" maxlength="80" /></el-form-item>
        <el-form-item :label="isDsh ? '平台地址' : 'Base URL'">
          <el-input v-model="form.base_url" placeholder="https://api.example.com/v1" />
        </el-form-item>
        <template v-if="isDsh">
          <el-form-item label="App ID"><el-input v-model="form.app_id" maxlength="200" /></el-form-item>
          <el-form-item :label="form.has_api_key ? 'App Secret（留空则不修改）' : 'App Secret'">
            <el-input v-model="form.api_key" type="password" show-password />
          </el-form-item>
          <el-form-item label="专家">
            <div style="display: flex; gap: 8px; width: 100%">
              <el-select v-model="form.agent_id" placeholder="先拉取专家列表" filterable style="flex: 1">
                <el-option v-for="expert in experts" :key="expert.agent_id" :label="expert.name" :value="expert.agent_id" />
                <el-option v-if="form.agent_id && !experts.some((item) => item.agent_id === form.agent_id)" :label="form.model_name || form.agent_id" :value="form.agent_id" />
              </el-select>
              <el-button :loading="expertsLoading" @click="loadExperts">拉取专家列表</el-button>
            </div>
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item :label="form.has_api_key ? 'API Key（留空则不修改）' : 'API Key'">
            <el-input v-model="form.api_key" type="password" show-password placeholder="Ollama 通常可以留空" />
          </el-form-item>
          <el-form-item label="模型名"><el-input v-model="form.model_name" placeholder="qwen-plus" /></el-form-item>
          <el-form-item label="温度">
            <el-slider v-model="form.temperature" :min="0" :max="2" :step="0.1" show-input />
          </el-form-item>
          <el-form-item label="max_tokens">
            <el-input-number v-model="form.max_tokens" :min="1" :max="32768" />
          </el-form-item>
          <el-form-item label="系统提示词 / 人设">
            <el-input v-model="form.system_prompt" type="textarea" :rows="5" placeholder="你是展厅讲解员，说话短、口语化。" />
          </el-form-item>
        </template>
      </el-form>
      <div v-if="testResult" class="test-box">
        <el-alert v-if="testResult.ok" type="success" :closable="false" :title="`已连通 · ${testResult.latency_ms} ms`" :description="testResult.reply" />
        <el-alert v-else type="error" :closable="false" title="连接失败" :description="testResult.error" />
      </div>
      <template #footer>
        <el-button v-if="isDsh" type="success" @click="openVerifyFromForm">验证测试</el-button>
        <el-button v-else :loading="testing" @click="testBrain">测试连接</el-button>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="verifyVisible" title="验证测试 · DeepSeek Harness 专家" width="640px">
      <el-form label-position="top">
        <el-form-item label="测试问题">
          <el-input v-model="verifyCtx.question" type="textarea" :rows="2" maxlength="500" />
        </el-form-item>
      </el-form>
      <div v-if="verifyResult" class="test-box">
        <div v-for="(step, index) in verifyResult.steps" :key="index" style="margin: 4px 0">
          <span :style="{ color: step.ok ? '#67c23a' : '#f56c6c' }">{{ step.ok ? "✔" : "✘" }}</span>
          {{ step.name }} · {{ step.ms }} ms<span v-if="step.detail"> · {{ step.detail }}</span>
        </div>
        <el-alert v-if="verifyResult.ok" type="success" :closable="false" style="margin-top: 10px" :title="`验证通过 · 专家：${verifyResult.agent_name}`" :description="verifyResult.reply" />
        <el-alert v-else-if="verifyResult.error" type="error" :closable="false" style="margin-top: 10px" title="验证失败" :description="verifyResult.error" />
      </div>
      <template #footer>
        <el-button @click="verifyVisible = false">关闭</el-button>
        <el-button type="primary" :loading="verifying" @click="runVerify">开始验证</el-button>
      </template>
    </el-dialog>
  </div>
</template>
