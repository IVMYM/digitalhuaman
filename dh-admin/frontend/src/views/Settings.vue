<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { api, setSession } from "../api";

const saving = ref(false);
const status = ref(null);
const form = reactive({ old_password: "", new_password: "", again: "" });

onMounted(async () => {
  try {
    const data = await api("/api/dashboard");
    status.value = data.status;
  } catch (error) {
    ElMessage.error(error.message);
  }
});

async function submit() {
  if (form.new_password.length < 8) {
    ElMessage.warning("新密码至少 8 位");
    return;
  }
  if (form.new_password !== form.again) {
    ElMessage.warning("两次输入的新密码不一致");
    return;
  }
  saving.value = true;
  try {
    const data = await api("/api/auth/change-password", {
      method: "POST",
      json: { old_password: form.old_password, new_password: form.new_password },
    });
    setSession(data.access_token, data.username);
    form.old_password = "";
    form.new_password = "";
    form.again = "";
    ElMessage.success("密码已更新");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="grid-2">
    <article class="panel" style="padding: 8px 18px 22px">
      <div class="panel-bar" style="padding-left: 0">
        <div>
          <h2>修改密码</h2>
          <p>只改数据库里的管理员密码。之后重启不会再用 .env 里的初始密码覆盖。</p>
        </div>
      </div>
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="原密码"><el-input v-model="form.old_password" type="password" show-password /></el-form-item>
        <el-form-item label="新密码"><el-input v-model="form.new_password" type="password" show-password /></el-form-item>
        <el-form-item label="再输入一次"><el-input v-model="form.again" type="password" show-password /></el-form-item>
        <el-button type="primary" :loading="saving" @click="submit">更新密码</el-button>
      </el-form>
    </article>
    <article class="panel">
      <div class="panel-bar">
        <div>
          <h2>运行时</h2>
          <p>LiveTalking 使用 RUNTIME_API_TOKEN，不要把大脑的真实 API Key 放到 GPU 机器上。</p>
        </div>
      </div>
      <dl v-if="status" class="status">
        <div>
          <dt>令牌</dt>
          <dd>{{ status.runtime_token_configured ? "已配置" : "未配置，运行时接口不可用" }}</dd>
        </div>
        <div>
          <dt>数据目录</dt>
          <dd>{{ status.data_dir }}</dd>
        </div>
        <div>
          <dt>版本</dt>
          <dd>{{ status.version }}</dd>
        </div>
      </dl>
    </article>
  </div>
</template>
