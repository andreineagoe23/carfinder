#!/usr/bin/env bash
# Search results live on the `results` branch, checked out as a worktree in ./results.
#   results-branch.sh checkout          check out (or create) the branch
#   results-branch.sh push "<message>"  commit and push any changes
set -euo pipefail
BRANCH=results
DIR=results

case "${1:-}" in
  checkout)
    git config user.name "carfinder-bot"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null; then
      git fetch --depth=1 origin "$BRANCH"
      git worktree add -B "$BRANCH" "$DIR" "origin/$BRANCH"
    else
      git worktree add --orphan -b "$BRANCH" "$DIR"
    fi
    ;;
  push)
    cd "$DIR"
    git add -A
    if git diff --cached --quiet; then
      echo "No changes to results"
      exit 0
    fi
    git commit -q -m "${2:-update results}"
    git push origin "$BRANCH"
    ;;
  *)
    echo "usage: $0 checkout | push <message>" >&2
    exit 2
    ;;
esac
