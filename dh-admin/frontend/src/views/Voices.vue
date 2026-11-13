<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api, apiBlob, upload } from "../api";
import { labelOf, voiceEngines } from "../options";

const loading = ref(false);
const saving = ref(false);
const rows = ref([]);
const visible = ref(false);
const audioFile = ref(null);
const audioUrl = ref("");
const form = reactive(blank());

function blank() {
  return { id: null, name: "", engine: "edge-tts", endpoint_url: "", voice_id: "", has_reference: false, reference_filename: "" };
}

async function load() {
  loading.value = true;
  try {
    rows.value = await api("/api/voices");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  Object.assign(form, blank());
  audioFile.value = null;
  clearAudio();
  visible.value = true;
}

async function openEdit(row) {
  Object.assign(form, { ...blank(), ...row });
  audioFile.value = null;
  clearAudio();
  visible.value = true;
  if (row.has_reference) {
    try {
      const blob = await apiBlob(`/api/voices/${row.id}/reference`);
      audioUrl.value = URL.createObjectURL(blob);
    } catch {
      audioUrl.value = "";
    }
  }
}

function clearAudio() {
  if (audioUrl.value) URL.revokeObjectURL(audioUrl.value);
  audioUrl.value = "";
}

async function save() {
  saving.value = true;
  try {
    const payload = {
      name: form.name,
      engine: form.engine,
      endpoint_url: form.endpoint_url,
      voice_id: form.voice_id,
    };
    const path = form.id ? `/api/voices/${form.id}` : "/api/voices";
    const method = form.id ? "PUT" : "POST";
    const saved = await api(path, { method, json: payload });
    if (audioFile.value) await upload(`/api/voices/${saved.id}/reference`, audioFile.value);
    ElMessage.success("声音已保存");
    visible.value = false;
    await load();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`删除声音「${row.name}」？`, "删除声音", { type: "warning" });
  try {
    await api(`/api/voices/${row.id}`, { method: "DELETE" });
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
        <h2>声音</h2>
        <p>Edge TTS 通常只需要音色名。CosyVoice、GPT-SoVITS、Fish Speech 再填服务地址和参考音频。</p>
      </div>
      <el-button type="primary" @click="openCreate">新建声音</el-button>
    </div>
    <el-table :data="rows">
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column label="引擎" min-width="140">
        <template #default="{ row }">{{ labelOf(voiceEngines, row.engine) }}</template>
      </el-table-column>
      <el-table-column prop="voice_id" label="音色 ID" min-width="180" />
      <el-table-column prop="endpoint_url" label="服务地址" min-width="200" show-overflow-tooltip />
      <el-table-column label="参考音频" min-width="140">
        <template #default="{ row }">{{ row.has_reference ? row.reference_filename : "无" }}</template>
      </el-table-column>
      <el-table-column label="LiveTalking" width="130">
        <template #default="{ row }">{{ row.livetalking_tts || "—" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty><el-empty description="还没有声音" /></template>
    </el-table>

    <el-dialog v-model="visible" :title="form.id ? '编辑声音' : '新建声音'" width="560px" @closed="clearAudio">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" maxlength="80" /></el-form-item>
        <el-form-item label="引擎">
          <el-select v-model="form.engine" style="width: 100%">
            <el-option v-for="item in voiceEngines" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="服务地址">
          <el-input v-model="form.endpoint_url" placeholder="Edge TTS 可留空，例如 http://127.0.0.1:9880" />
        </el-form-item>
        <el-form-item label="音色 ID / 参考名">
          <el-input v-model="form.voice_id" placeholder="例如 zh-CN-YunxiaNeural" />
        </el-form-item>
        <el-form-item label="参考音频">
          <div class="file-row">
            <input type="file" accept="audio/*" @change="audioFile = $event.target.files?.[0] || null" />
            <span>{{ audioFile?.name || form.reference_filename || "wav / mp3" }}</span>
          </div>
          <audio v-if="audioUrl" :src="audioUrl" controls style="margin-top: 8px; width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
