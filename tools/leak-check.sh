#!/usr/bin/env bash
# Leak check for this public repo. Run it before every commit and every push (see AGENTS.md).
#
#   tools/leak-check.sh          unpushed commits (changes and messages) and uncommitted changes
#   tools/leak-check.sh --all    the whole history and uncommitted changes
#
# It looks for the real deployment values, extra private strings, tokens, private keys,
# absolute local paths and email addresses other than placeholders. Private values are
# shown as <private> in the output. Exit 0: nothing found. Exit 1: findings to review.
# Exit 2: the check could not run.
#
# The real values (board domain, D1 database ID, Access team domain and AUD tag) are read
# from data/wrangler.toml in the private data repo. More private strings (server names,
# personal email addresses, ...) go in data/leak-patterns.txt, one per line.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

config=data/wrangler.toml
extra=data/leak-patterns.txt
if [[ ! -f $config ]]; then
  echo "leak-check: $config is missing, so the real domain and Access IDs cannot be checked." >&2
  exit 2
fi

patterns=$(mktemp)
trap 'rm -f "$patterns"' EXIT
sed -nE 's/.*(pattern|database_id|TEAM_DOMAIN|POLICY_AUD) *= *"([^"<]+)".*/\2/p' "$config" > "$patterns"
if [[ ! -s $patterns ]]; then
  echo "leak-check: no deployment values found in $config." >&2
  exit 2
fi
if [[ -f $extra ]]; then
  grep -v -e '^#' -e '^[[:space:]]*$' "$extra" >> "$patterns" || true
fi

if [[ ${1:-} == --all ]]; then
  range=(--all)
  label='the whole history'
elif [[ -z ${1:-} ]]; then
  upstream=$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null) || {
    echo "leak-check: this branch has no upstream; use --all." >&2
    exit 2
  }
  range=("$upstream..HEAD")
  label="$upstream..HEAD"
else
  echo "usage: tools/leak-check.sh [--all]" >&2
  exit 2
fi

# Commit messages and changed lines (no context lines), then uncommitted and new files.
changes() {
  git log -p -U0 --no-color --no-ext-diff --format='==> commit %h%n%B' "${range[@]}"
  echo '==> uncommitted changes'
  git diff -U0 --no-color --no-ext-diff HEAD
  git ls-files -z -o --exclude-standard | while IFS= read -r -d '' f; do
    printf 'diff --git a/%s b/%s\n' "$f" "$f"
    grep -I '' "$f" | sed 's/^/+/' || true
  done
}

changes | awk -v pfile="$patterns" -v label="$label" '
  function mask(s,    k, i) {
    for (i = 1; i <= n; i++) {
      while ((k = index(tolower(s), pats[i])) > 0)
        s = substr(s, 1, k - 1) "<private>" substr(s, k + length(pats[i]))
    }
    return s
  }
  BEGIN { while ((getline p < pfile) > 0) if (p != "") pats[++n] = tolower(p) }
  /^==> / { where = substr($0, 5); file = "message"; next }
  /^diff --git / { file = substr($NF, 3); next }
  /^(index |--- |\+\+\+ |@@ |Binary files |new file mode |deleted file mode |old mode |new mode )/ { next }
  {
    # Drop the diff marker so a "+" or "-" does not join the text next to it.
    text = ($0 ~ /^[+-]/ && file != "message") ? substr($0, 2) : $0
    low = tolower(text); hit = ""
    for (i = 1; i <= n && !hit; i++) if (index(low, pats[i])) hit = "private value"
    if (!hit && text ~ /gh[pousr]_[A-Za-z0-9]{20}|github_pa[t]_|PRIVATE[ ]KEY|eyJ[A-Za-z0-9_-]{15,}\.eyJ/) hit = "token or key"
    if (!hit && text ~ /\/home\/|\/Users\/|[A-Za-z]:\\Users\\/) hit = "local path"
    if (!hit && low ~ /[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z][a-z]+/ && low !~ /@example\.(org|com)|git@github\.com|noreply\.github\.com/) hit = "email address"
    if (hit) {
      found++
      printf "%s, %s: %s\n    %s\n", where, file, hit, substr(mask($0), 1, 200)
    }
  }
  END {
    if (found) { printf "leak-check: %d finding(s) in %s and uncommitted changes.\n", found, label; exit 1 }
    printf "leak-check: nothing found in %s and uncommitted changes.\n", label
  }'
