#!/usr/bin/env bash
# Deploy the fare system to KENET (vm-app, 197.137.65.49) from this laptop:
#
#   bash bus-fare/deploy-kenet.sh
#
# Ships the COMMITTED bus-fare/ folder of HEAD (not uncommitted edits) to
# /opt/nextup/src/corporate on vm-app, builds the nextup-busfare image there,
# restarts only busfare-web and waits for /api/health/. If it doesn't come up
# healthy, the previous image is put back. Migrations run as the container starts.
#
# Needs your KENET admin key (~/.ssh/kenet_rsa). Settings and secrets live on the
# VM (/opt/nextup/env/busfare.env and /opt/nextup/.env), never in this repo.
# See DEPLOY.md, "KENET".
set -euo pipefail

VM=${KENET_VM:-197.137.65.49}
SSH=(ssh -i "$HOME/.ssh/kenet_rsa" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=15 "user@$VM")

cd "$(git rev-parse --show-toplevel)"
if [ -n "$(git status --porcelain -- bus-fare ':!bus-fare/reports')" ]; then
  echo "Note: bus-fare/ has uncommitted changes; they are NOT deployed (only HEAD is)."
fi
sha=$(git rev-parse --short HEAD)
echo "== 1. copy bus-fare/ at $sha to vm-app"
git archive --format=tar HEAD bus-fare | "${SSH[@]}" '
  set -e; cd /opt/nextup/src
  rm -rf corporate.new; mkdir corporate.new; tar -x -C corporate.new
  echo '"$sha"' > corporate.new/bus-fare/DEPLOYED_COMMIT
  rm -rf corporate; mv corporate.new corporate'

echo "== 2. build on vm-app (in the background, so a dropped SSH session can't stop it)"
"${SSH[@]}" '
  cd /opt/nextup
  docker image inspect nextup-busfare:latest >/dev/null 2>&1 && docker tag nextup-busfare:latest nextup-busfare:previous
  rm -f busfare-build.rc
  nohup sh -c "docker compose build busfare-web > busfare-build.log 2>&1; echo \$? > busfare-build.rc" >/dev/null 2>&1 &'
for _ in $(seq 120); do
  rc=$("${SSH[@]}" 'cat /opt/nextup/busfare-build.rc 2>/dev/null' || true)
  [ -n "$rc" ] && break
  sleep 10
done
if [ "${rc:-}" != 0 ]; then
  echo "BUILD_FAILED (exit ${rc:-timeout}). Last lines of the build log:"
  "${SSH[@]}" 'tail -25 /opt/nextup/busfare-build.log'
  exit 1
fi

echo "== 3. restart busfare-web and wait for it"
"${SSH[@]}" '
  cd /opt/nextup
  wait_healthy() {
    for _ in $(seq 48); do
      h=$(docker inspect -f "{{.State.Health.Status}}" "$(docker compose ps -q busfare-web)" 2>/dev/null || echo none)
      [ "$h" = healthy ] && return 0
      [ "$h" = unhealthy ] && return 1
      sleep 5
    done
    return 1
  }
  docker compose up -d --no-deps --force-recreate busfare-web
  if wait_healthy; then
    echo "DEPLOYED '"$sha"'"; echo "$(date -Is) DEPLOYED busfare '"$sha"' (laptop)" >> deploys.log
    docker image prune -f >/dev/null 2>&1 || true
    exit 0
  fi
  echo "FAILED: last log lines:"; docker compose logs --tail 30 busfare-web
  if docker image inspect nextup-busfare:previous >/dev/null 2>&1; then
    docker tag nextup-busfare:previous nextup-busfare:latest
    docker compose up -d --no-deps --force-recreate busfare-web
    wait_healthy && echo "ROLLED_BACK to the previous image" || echo "ROLLBACK_ALSO_FAILED"
  fi
  echo "$(date -Is) FAILED busfare '"$sha"' (laptop)" >> deploys.log
  exit 1'

echo "== 4. from the internet"
curl -fsS -m 20 "https://9two5.nextup.co.ke/api/health/" && echo
