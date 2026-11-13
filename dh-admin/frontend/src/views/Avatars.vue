<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api, upload } from "../api";
import { avatarTypes, labelOf } from "../options";
import Thumb from "../components/Thumb.vue";

const loading = ref(false);
const saving = ref(false);
const rows = ref([]);
const voices = ref([]);
const visible = ref(false);
const previewFile = ref(null);
const sourceFile = ref(null);
const form = reactive(blank());

function blank() {
  return {
    id: null,
    name: "",
    type: "wav2lip",
    livetalking_avatar_id: "",
    default_voice_id: null,
    is_default: false,
  };
}

async function load() {
  loading.value = true;
  try {
    const [avatarRows, voiceRows] = await Promise.all([api("/api/avatars"), api("/api/voices")]);
    rows.value = avatarRows;
    voices.value = voiceRows;
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  Object.assign(form, blank());
  previewFile.value = null;
  sourceFile.value = null;
  visible.value = true;
}

function openEdit(row) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    type: row.type,
    livetalking_avatar_id: row.livetalking_avatar_id,
    default_voice_id: row.default_voice_id,
    is_default: row.is_default,
  });
  previewFile.value = null;
  sourceFile.value = null;
  visible.value = true;
}

async function save() {
  saving.value = true;
  try {
    const payload = {
      name: form.name,
      type: form.type,
      livetalking_avatar_id: form.livetalking_avatar_id,
      default_voice_id: form.default_voice_id,
      is_default: form.is_default,
    };
    const path = form.id ? `/api/avatars/${form.id}` : "/api/avatars";
    const method = form.id ? "PUT" : "POST";
    const saved = await api(path, { method, json: payload });
    if (previewFile.value) await upload(`/api/avatars/${saved.id}/preview`, previewFile.value);
    if (sourceFile.value) await upload(`/api/avatars/${saved.id}/source`, sourceFile.value);
    ElMessage.success("形象已保存");
    visible.value = false;
    await load();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`删除形象「${row.name}」？已上传的文件会一起删除。`, "删除形象", { type: "warning" });
  try {
    await api(`/api/avatars/${row.id}`, { method: "DELETE" });
    ElMessage.success("已删除");
    await load();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

function pick(event, target) {
  const file = event.target.files?.[0] || null;
  if (target === "preview") previewFile.value = file;
  else sourceFile.value = file;
}

onMounted(load);
</script>

<template>
  <div class="panel table-wrap" v-loading="loading">
    <div class="panel-bar">
      <div>
        <h2>形象</h2>
        <p>avatar_id 要和 GPU 服务器上 LiveTalking 的 <code>data/avatars</code> 目录名一致。源视频存在本机，不会自动同步过去。</p>
      </div>
      <el-button type="primary" @click="openCreate">新建形象</el-button>
    </div>
    <el-table :data="rows">
      <el-table-column label="预览" width="80">
        <template #default="{ row }">
          <Thumb v-if="row.has_preview" :id="row.id" />
          <span v-else class="thumb placeholder">无图</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column label="类型" min-width="180">
        <template #default="{ row }">{{ labelOf(avatarTypes, row.type) }}</template>
      </el-table-column>
      <el-table-column prop="livetalking_avatar_id" label="avatar_id" min-width="160" />
      <el-table-column prop="default_voice_name" label="默认声音" min-width="120" />
      <el-table-column label="素材" min-width="100">
        <template #default="{ row }">{{ row.has_source ? row.source_filename : "未上传" }}</template>
      </el-table-column>
      <el-table-column label="默认" width="80">
        <template #default="{ row }">
          <el-tag v-if="row.is_default" type="warning">默认</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty><el-empty description="还没有形象" /></template>
    </el-table>

    <el-dialog v-model="visible" :title="form.id ? '编辑形象' : '新建形象'" width="560px">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" maxlength="80" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.type" style="width: 100%">
            <el-option v-for="item in avatarTypes" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="LiveTalking avatar_id">
          <el-input v-model="form.livetalking_avatar_id" placeholder="例如 wav2lip256_avatar1" />
        </el-form-item>
        <el-form-item label="默认声音">
          <el-select v-model="form.default_voice_id" clearable placeholder="可选" style="width: 100%">
            <el-option v-for="item in voices" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="设为默认形象"><el-switch v-model="form.is_default" /></el-form-item>
        <el-form-item label="预览图">
          <div class="file-row">
            <input type="file" accept="image/*" @change="pick($event, 'preview')" />
            <span>{{ previewFile?.name || "jpg / png / webp / gif" }}</span>
          </div>
        </el-form-item>
        <el-form-item label="源视频或素材">
          <div class="file-row">
            <input type="file" @change="pick($event, 'source')" />
            <span>{{ sourceFile?.name || "mp4 / zip / png 等" }}</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
