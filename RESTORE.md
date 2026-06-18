# 灾难恢复指南 — OpenRouter 日报监控(本机服务器版)

本仓库是「本机服务器版 OpenRouter 监控日报」系统的**权威备份**。系统平时在办公室那台 Mac 上通过
launchd 常驻运行:每天 **08:05 爬数据、09:00 发飞书群日报**。本文件用于在原机器损坏时,在一台全新
Mac 上把整套系统完整恢复并继续运行。

## 备份包含什么
- **代码**:本仓库 `main` 分支(`scripts/` `pipeline/` `config/` `web/`)。
- **调度安装器**:`scripts/install_daily_server.py`、`scripts/install_model_provider_daily_launchd.py`、`scripts/setup_venv.sh`。
- **加密密钥包**:`backup/secrets-backup.tar.gz.enc`(AES-256-CBC / PBKDF2,**解密口令在你的密码管理器里,不在本仓库**)。内含:
  - `.env`(全部 API key / token / 看板口令 / 告警 open_id)
  - `.staticrypt.json`(看板加密盐)
  - `lark-cli/`(飞书凭据:`config.json` + `appsecret_*.enc` + `*_ou_*.enc` + `keychain-lark-cli-key.txt` 钥匙串 key 副本)
  - `RECOVERY_NOTES.txt`(飞书群 `chat_id`、飞书 `app_id`)
  - `data/data-snapshot.tar.gz`(历史数据 `input`+`output` 快照)

## 恢复步骤(全新 Mac)
1. **基础环境**:安装 Homebrew、Python 3;`brew install lark-cli`;
   `git clone https://github.com/noahchen2002/openrouter-observer-weekly.git ~/openrouter-observer-weekly && cd ~/openrouter-observer-weekly`
2. **虚拟环境 + 依赖 + 浏览器**:
   `bash scripts/setup_venv.sh` 然后 `.venv/bin/python -m playwright install chromium`
3. **解密密钥包**(口令从密码管理器取):
   ```bash
   openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
     -in backup/secrets-backup.tar.gz.enc -out /tmp/orobs-secrets.tar.gz
   mkdir -p /tmp/orobs-secrets && tar xzf /tmp/orobs-secrets.tar.gz -C /tmp/orobs-secrets
   ```
   把 `/tmp/orobs-secrets/.env`、`.staticrypt.json` 拷回仓库根目录。
4. **恢复飞书发报(lark-cli)**,二选一:
   - A. 把 `lark-cli/config.json` 放回 `~/.lark-cli/`;把 `appsecret_*.enc`、`*_ou_*.enc` 放回
     `~/Library/Application Support/lark-cli/`;再用 key 副本重建钥匙串:
     `security add-generic-password -s lark-cli -a lark-cli -w "$(cat /tmp/orobs-secrets/lark-cli/keychain-lark-cli-key.txt)"`
   - B. 直接重配:用 `RECOVERY_NOTES.txt` 里的 `app_id` + app secret(飞书开放平台→开发者后台→应用→凭证与基础信息)重新登录 lark-cli。
5. **重登 OpenRouter 抓取会话**:用持久化 profile 启动浏览器并手动登录 `openrouter.ai`:
   `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --user-data-dir="$HOME/.openrouter-observer/chrome-cdp" --remote-debugging-port=<见 cdp-browser plist>`,登录后关闭。
6. **安装 launchd 常驻任务**:
   ```bash
   .venv/bin/python -m scripts.install_daily_server --load \
     --chat-id <RECOVERY_NOTES 里的 FEISHU_CHAT_ID> --scrape-time 08:05 --push-time 09:00
   .venv/bin/python -m scripts.install_model_provider_daily_launchd   # 见脚本 --help
   ```
   常驻浏览器 / 看板服务 / keepawake:参照原 `~/Library/LaunchAgents/com.openrouter-observer.*.plist` 重建。
7. **验证**:手动跑一次发报,确认飞书群收到卡片:
   `.venv/bin/python -m scripts.local_daily_push`

## 注意
- 解密口令**不在本仓库**,在你的密码管理器。**口令丢失 = 此备份不可用**。
- 钥匙串(GitHub token、飞书 key)不随系统镜像迁移;新机器需用本包内副本重建或在飞书后台重新授权。
- `.env` 或数据有更新后,重跑备份流程刷新本加密包。
