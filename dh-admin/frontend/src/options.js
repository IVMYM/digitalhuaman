export const avatarTypes = [
  { value: "livetalking-musetalk", label: "LiveTalking · MuseTalk" },
  { value: "wav2lip", label: "LiveTalking · Wav2Lip" },
  { value: "ernerf", label: "LiveTalking · ER-NeRF" },
  { value: "live2d", label: "Live2D" },
  { value: "other", label: "其他" },
];

export const voiceEngines = [
  { value: "cosyvoice", label: "CosyVoice" },
  { value: "gpt-sovits", label: "GPT-SoVITS" },
  { value: "edge-tts", label: "Edge TTS" },
  { value: "fish-speech", label: "Fish Speech" },
  { value: "other", label: "其他" },
];

export function labelOf(options, value) {
  return options.find((item) => item.value === value)?.label || value || "—";
}

export function formatBytes(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function formatUptime(seconds) {
  const total = Number(seconds) || 0;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) return `${hours} 小时 ${minutes} 分钟`;
  if (minutes > 0) return `${minutes} 分钟`;
  return `${total} 秒`;
}
