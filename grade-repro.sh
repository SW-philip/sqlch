#!/usr/bin/env bash
# grade-repro.sh — reproducibility audit for sqlch
# run from the root of the sqlch repo

set -euo pipefail

PASS=0
FAIL=0
WARN=0
TOTAL=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

pass() { echo -e "  ${GREEN}✔${RESET} $1"; PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); }
fail() { echo -e "  ${RED}✗${RESET} $1"; FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); }
warn() { echo -e "  ${YELLOW}~${RESET} $1"; WARN=$((WARN+1)); TOTAL=$((TOTAL+1)); }
header() { echo -e "\n${CYAN}${BOLD}── $1${RESET}"; }

echo -e "${BOLD}sqlch reproducibility audit${RESET}"
echo "run from: $(pwd)"
echo "date:     $(date)"

########################################
header "Nix flake"
########################################

if [[ -f flake.nix ]]; then
  pass "flake.nix exists"
else
  fail "flake.nix missing"
fi

if [[ -f flake.lock ]]; then
  pass "flake.lock exists"
  # check if it's stale (modified more than 90 days ago)
  if [[ "$(uname)" == "Linux" ]]; then
    age=$(( ( $(date +%s) - $(stat -c %Y flake.lock) ) / 86400 ))
  else
    age=$(( ( $(date +%s) - $(stat -f %m flake.lock) ) / 86400 ))
  fi
  if (( age > 90 )); then
    warn "flake.lock is ${age} days old — consider running 'nix flake update'"
  else
    pass "flake.lock is fresh (${age} days old)"
  fi
else
  fail "flake.lock missing — inputs are not pinned"
fi

# check flake.nix references a real rev, not just "main"
if grep -q 'rev\s*=\s*"main"' pkgs/sqlch/default.nix 2>/dev/null; then
  fail "default.nix pins rev = \"main\" — not reproducible, use a commit hash"
elif grep -q 'rev\s*=' pkgs/sqlch/default.nix 2>/dev/null; then
  rev=$(grep 'rev\s*=' pkgs/sqlch/default.nix | head -1 | grep -oP '"[^"]+"')
  pass "default.nix pins rev to $rev"
fi

# check sha256 is not fakeHash or fakeSha256
if grep -qE 'fakeHash|fakeSha256' pkgs/sqlch/default.nix 2>/dev/null; then
  fail "default.nix uses fakeHash/fakeSha256 — not suitable for publishing"
elif grep -q 'sha256' pkgs/sqlch/default.nix 2>/dev/null; then
  pass "sha256 is set in default.nix"
else
  warn "sha256 not found in default.nix"
fi

# check for conflict markers
if git grep -l '<<<<<<' -- '*.nix' 2>/dev/null | grep -q .; then
  fail "unresolved merge conflict markers found in .nix files:"
  git grep -l '<<<<<<' -- '*.nix' | sed 's/^/       /'
else
  pass "no merge conflict markers in .nix files"
fi

########################################
header "Python packaging"
########################################

if [[ -f pyproject.toml ]]; then
  pass "pyproject.toml exists"
else
  fail "pyproject.toml missing"
fi

# check for pinned deps in pyproject.toml
if grep -qE '==|~=' pyproject.toml 2>/dev/null; then
  pass "pyproject.toml has pinned/constrained dependencies"
else
  warn "pyproject.toml has no pinned versions — fine for Nix, risky for pip installs"
fi

# check for requirements.txt (usually redundant with pyproject but worth noting)
if [[ -f requirements.txt ]]; then
  warn "requirements.txt exists alongside pyproject.toml — make sure they're in sync"
fi

# check setup.py (legacy)
if [[ -f setup.py ]]; then
  warn "setup.py found — consider migrating fully to pyproject.toml"
fi

########################################
header "Source hygiene"
########################################

# check .gitignore exists
if [[ -f .gitignore ]]; then
  pass ".gitignore exists"
else
  warn ".gitignore missing"
fi

# check for .env files committed
if git ls-files | grep -qE '\.env$|\.env\.'; then
  fail ".env file is tracked by git — may contain secrets"
else
  pass "no .env files tracked"
fi

# check for hardcoded /home/ or /root/ paths in python source
if grep -rn '/home/' sqlch/ 2>/dev/null | grep -v '__pycache__' | grep -q .; then
  warn "hardcoded /home/ paths found in source:"
  grep -rn '/home/' sqlch/ | grep -v '__pycache__' | sed 's/^/       /'
else
  pass "no hardcoded /home/ paths in sqlch/"
fi

if grep -rn '/root/' sqlch/ 2>/dev/null | grep -v '__pycache__' | grep -q .; then
  warn "hardcoded /root/ paths found in source:"
  grep -rn '/root/' sqlch/ | grep -v '__pycache__' | sed 's/^/       /'
else
  pass "no hardcoded /root/ paths in sqlch/"
fi

# check for hardcoded /nix/store paths in python source (should use env vars instead)
if grep -rn '/nix/store/' sqlch/ 2>/dev/null | grep -v '__pycache__' | grep -q .; then
  fail "hardcoded /nix/store/ paths in Python source — use env vars (MPV_BIN etc.) instead:"
  grep -rn '/nix/store/' sqlch/ | grep -v '__pycache__' | sed 's/^/       /'
else
  pass "no hardcoded /nix/store/ paths in sqlch/"
fi

# check that env vars set in postFixup are actually used in python
for var in MPV_BIN SQLCH_MPRIS_PLUGIN; do
  if grep -rq "$var" sqlch/ 2>/dev/null; then
    pass "$var is referenced in sqlch/ source"
  else
    warn "$var is set in postFixup but not found in sqlch/ source"
  fi
done

########################################
header "Runtime assumptions"
########################################

# check if sqlch shells out to mpv by name (should use MPV_BIN)
if grep -rn '"mpv"' sqlch/ 2>/dev/null | grep -v '__pycache__' | grep -q .; then
  fail 'shellout to "mpv" by name found — should use os.environ["MPV_BIN"] instead:'
  grep -rn '"mpv"' sqlch/ | grep -v '__pycache__' | sed 's/^/       /'
else
  pass 'no bare "mpv" shellouts found'
fi

if grep -rn "'mpv'" sqlch/ 2>/dev/null | grep -v '__pycache__' | grep -q .; then
  fail "shellout to 'mpv' by name found — should use MPV_BIN:"
  grep -rn "'mpv'" sqlch/ | grep -v '__pycache__' | sed 's/^/       /'
fi

# check for os.system usage (harder to make reproducible than subprocess)
if grep -rn 'os\.system(' sqlch/ 2>/dev/null | grep -v '__pycache__' | grep -q .; then
  warn "os.system() calls found — subprocess is more reproducible and safer:"
  grep -rn 'os\.system(' sqlch/ | grep -v '__pycache__' | sed 's/^/       /'
else
  pass "no os.system() calls"
fi

# check for tempfile usage (fine, just flag for awareness)
if grep -rn 'tempfile\|/tmp/' sqlch/ 2>/dev/null | grep -v '__pycache__' | grep -q .; then
  warn "tempfile or /tmp/ usage found — make sure cleanup is handled:"
  grep -rn 'tempfile\|/tmp/' sqlch/ | grep -v '__pycache__' | sed 's/^/       /'
fi

########################################
header "Nix build integrity"
########################################

# check pythonImportsCheck is present
if grep -q 'pythonImportsCheck' pkgs/sqlch/default.nix 2>/dev/null; then
  pass "pythonImportsCheck is set — import errors caught at build time"
else
  warn "pythonImportsCheck not set — consider adding it"
fi

# check doCheck
if grep -q 'doCheck = false' pkgs/sqlch/default.nix 2>/dev/null; then
  warn "doCheck = false — tests are skipped during nix build"
elif grep -q 'doCheck = true' pkgs/sqlch/default.nix 2>/dev/null; then
  pass "doCheck = true — tests run during nix build"
else
  warn "doCheck not explicitly set"
fi

# check wrapProgram is used (good practice for runtime deps)
if grep -q 'wrapProgram' pkgs/sqlch/default.nix 2>/dev/null; then
  pass "wrapProgram used in postFixup — runtime deps injected cleanly"
else
  warn "wrapProgram not found — runtime deps may not be injected"
fi

########################################
# Score
########################################

echo -e "\n${BOLD}────────────────────────────────${RESET}"
echo -e "${BOLD}Results:${RESET} $TOTAL checks"
echo -e "  ${GREEN}✔ passed: $PASS${RESET}"
echo -e "  ${YELLOW}~ warned: $WARN${RESET}"
echo -e "  ${RED}✗ failed: $FAIL${RESET}"

SCORE=$(( (PASS * 100) / TOTAL ))
echo ""
if [ "$SCORE" -ge 90 ]; then
  echo -e "${GREEN}${BOLD}Grade: A ($SCORE/100) — solid${RESET}"
elif [ "$SCORE" -ge 75 ]; then
  echo -e "${GREEN}Grade: B ($SCORE/100) — good, minor issues${RESET}"
elif [ "$SCORE" -ge 60 ]; then
  echo -e "${YELLOW}Grade: C ($SCORE/100) — needs work${RESET}"
elif [ "$SCORE" -ge 40 ]; then
  echo -e "${YELLOW}Grade: D ($SCORE/100) — significant issues${RESET}"
else
  echo -e "${RED}Grade: F ($SCORE/100) — not reproducible${RESET}"
fi
echo ""
