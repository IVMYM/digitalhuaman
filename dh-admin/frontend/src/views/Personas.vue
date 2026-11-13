<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";

const loading = ref(false);
const saving = ref(false);
const rows = ref([]);
const avatars = ref([]);
const brains = ref([]);
const voices = ref([]);
const bases = ref([]);
const visible = ref(false);
const form = reactive(blank());

function blank() {
  return {
    id: null,
    name: "",
    description: "",
    avatar_id: null,
    brain_id: null,
    voice_id: null,
    knowledge_base_id: null,
    enabled: true,
    is_default: false,
  };
}

async function load() {
  loading.value = true;
  try {
    const [personaRows, avatarRows, brainRows, voiceRows, baseRows] = await Promise.all([
      api("/api/personas"),
      api("/api/avatars"),
      api("/api/brains"),
      api("/api/voices"),
      api("/api/knowledge-bases"),
    ]);
    rows.value = personaRows;
    avatars.value = avatarRows;
    brains.value = brainRows;
    voices.value = voiceRows;
    bases.value = baseRows;
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  Object.assign(form, blank());
  visible.value = true;
}

function openEdit(row) {
  Object.assign(form, { ...blank(), ...row });
  visible.value = true;
}

function payloadOf(source) {
  return {
    name: source.name,
    description: source.description || "",
    avatar_id: source.avatar_id,
    brain_id: source.brain_id,
    voice_id: source.voice_id,
    knowledge_base_id: source.knowledge_base_id,
    enabled: source.enabled,
    is_default: source.is_default,
  };
}

async function save() {
  saving.value = true;
  try {
    const path = form.id ? `/api/personas/${form.id}` : "/api/personas";
    const method = form.id ? "PUT" : "POST";
    await api(path, { method, json: payloadOf(form) });
    ElMessage.success("角色已保存");
    visible.value = false;
    await load();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}

async function patch(row, changes) {
  try {
    await api(`/api/personas/${row.id}`, { method: "PUT", json: payloadOf({ ...row, ...changes }) });
    await load();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`删除角色「${row.name}」？`, "删除角色", { type: "warning" });
  try {
    await api(`/api/personas/${row.id}`, { method: "DELETE" });
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
        <h2>数字人角色</h2>
        <p>一个角色绑一个形象、一个大脑、一个声音，知识库可选。LiveTalking 不指定角色时，会走启用中的默认角色。</p>
      </div>
      <el-button type="primary" @click="openCreate">新建角色</el-button>
    </div>
    <el-table :data="rows">
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="avatar_name" label="形象" min-width="120" />
      <el-table-column prop="brain_name" label="大脑" min-width="120" />
      <el-table-column prop="voice_name" label="声音" min-width="120" />
      <el-table-column label="知识库" min-width="120">
        <template #default="{ row }">{{ row.knowledge_base_name || "—" }}</template>
      </el-table-column>
      <el-table-column label="启用" width="90">
        <template #default="{ row }">
          <el-switch :model-value="row.enabled" @change="patch(row, { enabled: $event, is_default: $event ? row.is_default : false })" />
        </template>
      </el-table-column>
      <el-table-column label="默认" width="90">
        <template #default="{ row }">
          <el-switch :model-value="row.is_default" @change="patch(row, { is_default: $event, enabled: $event ? true : row.enabled })" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty><el-empty description="还没有角色。先去准备形象、大脑和声音。" /></template>
    </el-table>

    <el-dialog v-model="visible" :title="form.id ? '编辑角色' : '新建角色'" width="560px">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" maxlength="80" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="形象">
          <el-select v-model="form.avatar_id" style="width: 100%" placeholder="选择形象">
            <el-option v-for="item in avatars" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="大脑">
          <el-select v-model="form.brain_id" style="width: 100%" placeholder="选择大脑">
            <el-option v-for="item in brains" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="声音">
          <el-select v-model="form.voice_id" style="width: 100%" placeholder="选择声音">
            <el-option v-for="item in voices" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="知识库">
          <el-select v-model="form.knowledge_base_id" clearable placeholder="可选" style="width: 100%">
            <el-option v-for="item in bases" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
        <el-form-item label="作为默认角色"><el-switch v-model="form.is_default" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
