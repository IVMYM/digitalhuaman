# Colab `google-gpu` 初始化

在 Colab GPU Runtime 中运行。先填入固定授权 Key：

```python
import os
os.environ["TS_AUTHKEY"] = "tskey-auth-REPLACE_ME"
%run /content/colab_google_gpu_bootstrap.py
```

如果脚本文件还没上传，可把 `colab_google_gpu_bootstrap.py` 上传到 Colab 后再执行。

脚本会完成：

1. 写入 NVIDIA 动态库配置并执行 `ldconfig`；
2. 写入全局 PATH/LD_LIBRARY_PATH；
3. 安装 Tailscale 和 OpenSSH Server；
4. 以 `tailscaled --tun=userspace-networking` 启动后，再用 `TS_AUTHKEY` 执行 `tailscale up`；
5. 输出 `nvidia-smi`、当前 Tailscale IPv4，以及不随实例变化的 MagicDNS 地址 `colab-livetalking.YOUR-HOST.ts.net`。节点使用 `--ephemeral`，实例回收后自动从网络中注销，下次仍占用同一主机名。

