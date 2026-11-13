<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api, upload } from "../api";
import { formatBytes, formatTime } from "../options";

const loading = ref(false);
const bases = ref([]);
const documents = ref([]);
const currentId = ref(null);
const visible = ref(false);
const file = ref(null);
const form = reactive({ id: null, name: "", description: "" });
const current = computed(() => bases.value.find((item) => item.id === currentId.value));

async function loadBases() {
  loading.value = true;
  try {
    bases.value = await api("/api/knowledge-bases");
    if (!currentId.value && bases.value.length) currentId.value = bases.value[0].id;
    if (currentId.value && !bases.value.some((item) => item.id === currentId.value)) {
      currentId.value = bases.value[0]?.id || null;
    }
    if (currentId.value) await loadDocs();
    else documents.value = [];
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function loadDocs() {
  documents.value = await api(`/api/knowledge-bases/${currentId.value}/documents`);
}

async function selectBase(id) {
  currentId.value = id;
  try {
    await loadDocs();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

function openCreate() {
  form.id = null;
  form.name = "";
  form.description = "";
  visible.value = true;
}

async function saveBase() {
  try {
    const payload = { name: form.name, description: form.description };
    if (form.id) await api(`/api/knowledge-bases/${form.id}`, { method: "PUT", json: payload });
    else {
      const created = await api("/api/knowledge-bases", { method: "POST", json: payload });
      currentId.value = created.id;
    }
    visible.value = false;
    await loadBases();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function removeBase(row) {
  await ElMessageBox.confirm(`删除知识库「${row.name}」及其文档？引用它的角色会取消关联。`, "删除知识库", { type: "warning" });
  try {
    await api(`/api/knowledge-bases/${row.id}`, { method: "DELETE" });
    if (currentId.value === row.id) currentId.value = null;
    await loadBases();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function uploadDoc() {
  if (!file.value || !currentId.value) return;
  try {
    await upload(`/api/knowledge-bases/${currentId.value}/documents`, file.value);
    file.value = null;
    ElMessage.success("文档已上传");
    await loadBases();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function removeDoc(row) {
  await ElMessageBox.confirm(`删除文档「${row.original_name}」？`, "删除文档", { type: "warning" });
  try {
    await api(`/api/knowledge-bases/${currentId.value}/documents/${row.id}`, { method: "DELETE" });
    await loadBases();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

onMounted(loadBases);
</script>

<template>
  <div class="split" v-loading="loading">
    <aside class="panel kb-list">
      <div class="panel-bar">
        <div>
          <h2>知识库</h2>
          <p>上传 txt、md、pdf。检索目前是关键词匹配。</p>
        </div>
      </div>
      <button
        v-for="item in bases"
        :key="item.id"
        class="kb-item"
        :class="{ active: item.id === currentId }"
        @click="selectBase(item.id)"
      >
        <strong>{{ item.name }}</strong>
        <span>{{ item.document_count }} 个文档</span>
      </button>
      <div style="padding: 8px 12px 12px">
        <el-button type="primary" plain @click="openCreate">新建知识库</el-button>
      </div>
    </aside>
    <section class="panel">
      <div class="panel-bar" v-if="current">
        <div>
          <h2>{{ current.name }}</h2>
          <p>{{ current.description || "没有说明。" }}检索接口已留出，后续可换成 RAGFlow，不在这个容器里跑向量模型。</p>
        </div>
        <el-button type="danger" plain @click="removeBase(current)">删除知识库</el-button>
      </div>
      <div v-else class="panel-bar"><h2>先建一个知识库</h2></div>
      <div v-if="current" style="padding: 0 18px 12px" class="file-row">
        <input type="file" accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf" @change="file = $event.target.files?.[0] || null" />
        <el-button :disabled="!file" @click="uploadDoc">上传</el-button>
        <span>{{ file?.name || "支持 txt / md / pdf" }}</span>
      </div>
      <el-table v-if="current" :data="documents">
        <el-table-column prop="original_name" label="文件" min-width="180" />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatBytes(row.size_bytes) }}</template>
        </el-table-column>
        <el-table-column label="文本" width="120">
          <template #default="{ row }">{{ row.has_text ? `${row.text_chars} 字` : "未提取" }}</template>
        </el-table-column>
        <el-table-column label="上传时间" min-width="150">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeDoc(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="这个知识库还没有文档" /></template>
      </el-table>
    </section>

    <el-dialog v-model="visible" title="新建知识库" width="480px">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" maxlength="80" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="saveBase">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
