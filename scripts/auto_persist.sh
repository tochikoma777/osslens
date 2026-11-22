#!/usr/bin/env bash
# 自动链并行回写（analyze / abstract 两个 job 共用）。
#
# 顺序：提交真源 → rebase 到最新 main → 在**合并后的真源**上重建站点 → 提交站点 → push。
# · 真源 JSONL 是 append-only，由 .gitattributes 的 merge=union 保留双方新增行；
# · 站点是派生基线，必须在合并后的真源上重建，避免两段各自提交互相覆盖；
# · push 失败（远端已推进）→ 回滚本次站点提交后重试，最多 5 次。
# 用法：scripts/auto_persist.sh "chore(auto): ..."
set -euo pipefail

message="${1:?用法: scripts/auto_persist.sh <commit-message>}"
bot_name="osslens-bot"
bot_email="osslens-bot@users.noreply.github.com"

# ★ 流水线身份修复（2026-11-22 增量复核 F1）：下面 commit 用 `git -c` 只作用于
#   单条命令；而 `git rebase`（第 2 步）重放提交时需要 committer identity，
#   GitHub runner 未配置全局 user.name/email → "empty ident name" / exit 128
#   （真实失败：run 44798310784 / 44598357662）。这里设仓库级身份，使 rebase
#   与任何 hook 都有身份；不设全局，不影响 runner 上其它仓库。
git config user.name "$bot_name"
git config user.email "$bot_email"

# 1) 真源先落本地提交（站点暂不提交，等 rebase 后重建）
git add -- data/costs data/abstract patterns reports data/featcards
if git diff --cached --quiet; then
  echo "[skip] 无真源变更，不产生提交"
  exit 0
fi
git -c user.name="$bot_name" -c user.email="$bot_email" commit -m "$message" >/dev/null

for attempt in 1 2 3 4 5; do
  # 2) 追平远端（merge=union 负责 append-only 的双方追加）
  git fetch origin main
  git rebase origin/main

  # 3) 在合并后的真源上重建站点，再单独提交（派生基线不参与 union）
  python -m osslens site
  site_committed=0
  if ! git diff --quiet -- site; then
    git add -- site
    git -c user.name="$bot_name" -c user.email="$bot_email" \
      commit -m "chore(auto): 重建站点 $(date -u +%Y-%m-%d)" >/dev/null
    site_committed=1
  fi

  if git push origin main; then
    echo "[ok] push 成功（第 ${attempt} 次）"
    exit 0
  fi

  # 4) push 失败：丢弃本次站点提交，重新拉取/重建/推送；真源提交保留
  echo "[retry] push 失败（第 ${attempt} 次），回滚站点提交后重试"
  if [ "$site_committed" = "1" ]; then
    git reset --mixed HEAD^ >/dev/null
    git checkout -- site
  fi
  sleep $((attempt * 3))
done

echo "[fail] 5 次重试后仍未 push 成功" >&2
exit 1
