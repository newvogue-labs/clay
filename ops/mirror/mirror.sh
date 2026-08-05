#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a; source "$DIR/.env"; set +a
REPOS=("clay" "clay-knowledge")
seed() { # name repo target_url
  local name="$1" repo="$2" url="$3" tmp
  tmp="$(mktemp -d)"
  git clone --mirror "https://github.com/newvogue-labs/${repo}.git" "$tmp/${repo}.git"
  git -C "$tmp/${repo}.git" push --mirror "$url"
  rm -rf "$tmp"
  echo "[$name] ${repo}: OK"
}
for repo in "${REPOS[@]}"; do
  [ -n "${GITLAB_TOKEN:-}" ] && seed gitlab "$repo" "https://oauth2:${GITLAB_TOKEN}@gitlab.com/newvogue-labs/${repo}.git"
  # GitFlic/Codeberg добавим позже по тому же образцу, когда будут токены и репо.
done
