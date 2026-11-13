<script setup>
import { onBeforeUnmount, ref, watch } from "vue";
import { apiBlob } from "../api";

const props = defineProps({ id: { type: Number, required: true } });
const url = ref("");

async function load(id) {
  if (url.value) URL.revokeObjectURL(url.value);
  url.value = "";
  try {
    const blob = await apiBlob(`/api/avatars/${id}/preview`);
    url.value = URL.createObjectURL(blob);
  } catch {
    url.value = "";
  }
}

watch(() => props.id, load, { immediate: true });
onBeforeUnmount(() => {
  if (url.value) URL.revokeObjectURL(url.value);
});
</script>

<template>
  <img v-if="url" :src="url" alt="" class="thumb" />
  <span v-else class="thumb placeholder">无图</span>
</template>
