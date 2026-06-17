# SiliconFlow Top 30 Base Sync

This automation reads SiliconFlow Top 30 report emails from Feishu Mail, downloads
the CSV/XLSX attachment, deduplicates users, and updates the Feishu Base table.

## Behavior

- Mail source: `SiliconFlowReporter <no-reply@siliconflow.cn>`.
- Default subject match: contains `Top 30 用户` and `有结果`.
- User key: `主账号用户ID`, falling back to `租户ID`, then `联系邮箱`.
- Incoming duplicate rows keep the best rank.
- Written fields:
  - `排名`
  - `租户ID`
  - `主账号用户ID`
  - `用户名`
  - `联系邮箱`
  - `消费金额`
  - `消费模型(Top5/按消费)`
  - `最近消费`
  - `活跃天数`
  - `标签`
  - `触达状态` only when creating a new record
- Ignored report fields:
  - `统计区间(周一~周三)`
  - `首次消费`

## Label Rules

- `新增`: a user is in the new report but was not in the previous in-rank set.
- `持续在榜`: a user was in the previous in-rank set and is still in the new report.
- `掉出榜`: a user was in the previous in-rank set but is not in the new report.

Records marked `掉出榜` remain in the table. If they appear in a later report,
the script marks them `新增` again and updates their ranking and usage fields.

## Manual Run

```bash
python3 scripts/top30_base_sync.py --dry-run
python3 scripts/top30_base_sync.py
```

Process one explicit email:

```bash
python3 scripts/top30_base_sync.py --message-id '<message_id>' --dry-run
python3 scripts/top30_base_sync.py --message-id '<message_id>' --force
```

## Schedule On macOS

The launchd installer runs the sync at 09:10 Monday and 12:10 Thursday by
default, giving the scheduled email a short delivery buffer.

```bash
python3 scripts/install_top30_base_sync_launchd.py --load
```

Unload it:

```bash
python3 scripts/install_top30_base_sync_launchd.py --unload
```

Logs:

```text
data/debug/launchd/top30_base_sync.out.log
data/debug/launchd/top30_base_sync.err.log
```

Processed email IDs are stored outside the repo:

```text
~/.local/state/siliconflow_top30_base_sync/state.json
```

## Configuration

The defaults target the existing Base URL shared in the setup conversation.
Override with environment variables when needed:

```bash
TOP30_BASE_TOKEN='base_token'
TOP30_TABLE_ID='table_id'
TOP30_MAILBOX='me'
TOP30_MAIL_QUERY='Top 30 用户'
TOP30_FROM_CONTAINS='no-reply@siliconflow.cn'
TOP30_STATE_PATH='~/.local/state/siliconflow_top30_base_sync/state.json'
TOP30_DOWNLOAD_DIR='~/Downloads/siliconflow_top30_base_sync'
LARK_CLI_BIN='/opt/homebrew/bin/lark-cli'
```

The script relies on `lark-cli` user authentication for Feishu Mail and Base.
