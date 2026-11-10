# 项目长期记忆 — glados-checkin

## 项目定位
GLaDOS 自动签到脚本（`checkin.py`），支持 GitHub Actions / cron-job.org / 本地 cron / NixOS systemd。
输出 PushPlus 微信推送 + Telegram 推送。

## 必须遵守的技术约定

1. **签到 token 必须与请求域名完全一致**（含 `www.` 前缀）。
   服务端会核对，不一致就返回 `please checkin via https://...`。
   因此**不要写死 token**，用 `GLaDOS.token_of(domain)` 从实际命中的域名生成。
2. **不要用 `code` 字段判断成功**。各接口语义不一致：
   - `POST /api/user/checkin` 成功 → `code = 1`
   - `GET /api/user/status` / `GET /api/user/points` 成功 → `code = 0`
   统一按 `message` 文案判断（见 `GLaDOS.is_success` + `FAIL_HINTS`）。
3. **成功/失败文案对照**：
   - ✅ `Today's observation logged. Return tomorrow for more points.`
   - ✅ `Checkin Repeats! Please Try Tomorrow`（今日已签）
   - ❌ `please checkin via https://...`
4. `POST /api/user/checkin` 响应里的 `points` 字段**恒为 0**，不是今日收益。
   今日收益取 `GET /api/user/points` → `history[0].change`（且 `detail` 需等于今天）。
   `streak` 字段是连续签到天数，可信。
5. `points` / `leftDays` 是**字符串**且带超长小数（如 `"38.0000000000000000"`），
   统一用 `str(x).split('.')[0]` 截断。
6. **2026-11 起服务端上线 Bot Challenge**（`GET /api/user/checkin/challenge`，
   返回 `{code:0, nonce, ttl:300000}`，ttl 5 分钟）。
   前端流程：领 nonce → 等约 2.6s → `proof = sha256(f"{nonce}.glados-observe-v1")`
   → `POST /api/user/checkin` body `{token, nonce, proof}`。
   注意：实测**纯 token 仍能返回 `code:1`**（但日常响应带 `"repeated":true`），
   所以服务端对挑战的强制程度尚未确认；`checkin.py` 采用「先挑战、拿不到 nonce 再回退纯 token」。
7. **新版 Cookie 只需 `gld:sess` + `gld:sess.sig`**（2026-11 起），
   老版 `koa:sess` / `koa:sess.sig` 仍兼容。`extract_cookie` 原样透传整串即可。

## 接口速查
| 接口 | 方法 | 关键字段 |
| --- | --- | --- |
| `/api/user/checkin/challenge` | GET | 返回 `nonce`（一次性，需在限定时间内提交 proof） |
| `/api/user/checkin` | POST | body `{"token","nonce","proof"}`；返回 `message` / `streak` / `reason` |
| `/api/user/status` | GET | `data.email` / `data.leftDays` / `data.system_date` |
| `/api/user/points` | GET | `points` / `history[]` / `plans`（plan100/200/500）/ `streak` |

## 多域名
`www.glados.vip`、`glados.one` 等均直连 Cloudflare 后端，无跳转，可互为回退。

## 环境备注
- 本机 Git Bash 缺 coreutils（`mkdir`/`head`/`dirname` 都不可用），需要 shell 工具时改用 PowerShell 工具或内置 Read/Write/Glob。
- 测试用 Python：`C:\Users\admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe`（已装 requests）。
