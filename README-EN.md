# digitalhuaman (LiveTalking-Muse experimental toolkit)

[中文](./README.md)

An **experimental** digital-human stack built on [LiveTalking](https://github.com/lipku/LiveTalking), plus local admin (`dh-admin`), integrated UI (`fine-digital-human`), and optional Colab/DSW/TURN helper scripts.

| Item | |
|------|-----|
| Repository name | **digitalhuaman** (publisher-chosen; not affiliated with upstream LiveTalking) |
| Upstream core license | Apache-2.0 — see [LICENSE](./LICENSE), [NOTICE](./NOTICE) |
| Third-party / models | **Required reading:** [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md) (Wav2Lip is **not** unrestricted commercial) |
| What ships | [docs/PUBLICATION_SCOPE.md](./docs/PUBLICATION_SCOPE.md) |

**No warranty** of a working end-to-end avatar call out of the box. Labels: *code-supported path*, *historical observation (not re-run in this release)*, *unverified*.

---

## vs upstream LiveTalking

- Same core engine (`app.py`, `server/`, `avatars/`).
- Adds **dh-admin** (roles, brains, runtime API) and **fine-digital-human** (browser shell).
- Default [config.yaml](./config.yaml): `llm_provider: dh-admin`, `webrtc`, example `avatar_id: wav2lip256_avatar1`.
- No model weights or private avatars in git — [docs/ASSETS_AND_MODELS.md](./docs/ASSETS_AND_MODELS.md).
- Upstream readme copy: [docs/README-UPSTREAM-LIVETALKING-en.md](./docs/README-UPSTREAM-LIVETALKING-en.md).

---

## Architecture (code-supported wiring)

Browser → **fine-digital-human** (:8000) → WebRTC `/offer` + `/human` → **LiveTalking** (:8010) → avatar backend (wav2lip / musetalk / ultralight).

Optional: LiveTalking LLM via **dh-admin** (:18200) OpenAI-compatible `/v1/chat/completions` ([llm.py](./llm.py)).

HTTP tunnels (Cloudflare, Colab TCP forward) may carry **signaling** only; WebRTC **media** often needs reachable STUN/TURN (*historical observation*, not universally proven impossible).

Default ports: 8010 / 18200 / 8000.

---

## Prerequisites

- **CUDA GPU** for lip-sync inference (no CPU fallback promised).
- Python 3.10+; Node for `dh-admin/frontend` builds only.
- Install **PyTorch** matching your CUDA stack before `pip install -r requirements.txt`.
- `websockets==12.0` may conflict with some Colab preinstalls (*historical note*).

---

## Smallest reproducible paths

### A — dh-admin unit tests (no GPU)

```bash
cd dh-admin/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

### B — full local stack (*unverified on your machine*)

1. Download weights and build `data/avatars/<avatar_id>/` per [docs/ASSETS_AND_MODELS.md](./docs/ASSETS_AND_MODELS.md).
2. `python app.py --config config.yaml`
3. `uvicorn app.main:app` in `dh-admin/backend` (configure `dh-admin/.env` from `.env.example`).
4. `uvicorn app:app` in `fine-digital-human` with matching `DH_ADMIN_RUNTIME_TOKEN`.

Copy `.env.example` files; never commit `.env` or `.secrets/`.

---

## Configuration

- Environment templates: root [`.env.example`](./.env.example), `dh-admin/`, `fine-digital-human/`.
- TURN template in [docs/ASSETS_AND_MODELS.md](./docs/ASSETS_AND_MODELS.md).
- Example Edge voice: `zh-CN-YunxiaNeural` (needs network access to Edge TTS).

---

## Troubleshooting

- Black video after SDP: ICE/media path; configure TURN.
- `Maximum session limit`: `max_session` in config.
- Colab: stopping a cell may not kill background `app.py` (*historical observation*).

---

## Historical observations (2026-11-03/04, Colab — **not re-tested for this release**)

- `torch 2.9.1+cu128`, Tesla T4, CUDA true — **detection only**, no verified lip-sync output.
- HTTP UI OK; trycloudflare signaling sometimes returned SDP; ~40s black frame, `connectionState` never `connected`.
- Session cap 5/5; TURN success **not** observed; `/sessionlist` route **not confirmed**.

---

## Limitations

- Vendored **Wav2Lip** code: upstream **non-commercial** terms; weights not redistributed here.
- `fine-digital-human/static/vendor/` omitted (~34MB); some browser features may be missing.
- Scripts may reference legacy avatar codenames (`zhengxin`); replace with your `avatar_id` — see [scripts/README.md](./scripts/README.md).

---

## Contributing

PRs welcome: no secrets, no weights, cite third-party licenses, state what you actually ran.

---

## Links

- [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md)
- [lipku/LiveTalking](https://github.com/lipku/LiveTalking)
