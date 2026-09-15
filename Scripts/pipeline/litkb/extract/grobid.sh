#!/usr/bin/env bash
# GROBID 0.9.1 (CRF) under WSL2 Ubuntu — idempotent install / start / stop / status.
#
# Path note: this lives beside the Python adapter rather than at a repo-root `scripts/wsl/`,
# because the repo root already carries `Scripts/` and Windows is case-insensitive: a
# lowercase `scripts/` sibling resolves to the SAME directory (verified 2026-09-14).
#
# Run as root inside the distro:
#   MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -u root -- bash <this> install|start|stop|status|health
#
# Resource budget (litkb decision litkb-p0-foundation §15.16: local workers keep 20% of RAM
# and CPU free for Kam). Measured on this host: 12 logical threads, 31 GiB visible to WSL.
#   usable CPU  = 12 * 0.8 = 9.6      -> concurrency 9
#   usable RAM  = 31 * 0.8 = 24.8 GiB
#   JVM heap 8 GiB (design §12.7 cites GROBID 6-8 GiB for batch)
#   + concurrency 9 * pdfalto cap 1.5 GiB = 13.5 GiB
#   = 21.5 GiB <= 24.8 GiB budget.
# The stock pdfalto cap is 6096 MB; 9 x that would be 54 GiB, far over budget, so it is
# lowered here. Override any of these by exporting the variables before calling.
set -euo pipefail

GROBID_VERSION="${GROBID_VERSION:-0.9.1}"
GROBID_DIR="${GROBID_DIR:-/opt/grobid-${GROBID_VERSION}}"
GROBID_PORT="${GROBID_PORT:-8070}"
GROBID_HEAP_GB="${GROBID_HEAP_GB:-8}"
GROBID_CONCURRENCY="${GROBID_CONCURRENCY:-9}"
GROBID_PDFALTO_MB="${GROBID_PDFALTO_MB:-1536}"
GROBID_PDFALTO_TIMEOUT="${GROBID_PDFALTO_TIMEOUT:-300}"
GROBID_JDK="${GROBID_JDK:-}"
UNIT=/etc/systemd/system/grobid.service
LAUNCHER="${GROBID_DIR}/grobid-service/build/install/grobid-service/bin/grobid-service"
CONFIG="${GROBID_DIR}/grobid-home/config/grobid.yaml"

log() { printf '[grobid.sh] %s\n' "$*"; }

find_jdk21() {
  if [ -n "$GROBID_JDK" ]; then printf '%s' "$GROBID_JDK"; return; fi
  ls -d /usr/lib/jvm/java-21-openjdk* 2>/dev/null | head -1
}

do_install() {
  export DEBIAN_FRONTEND=noninteractive
  if ! ls -d /usr/lib/jvm/java-21-openjdk* >/dev/null 2>&1; then
    log "installing JDK 21"
    apt-get update -qq
    apt-get install -y -qq openjdk-21-jdk-headless unzip curl ca-certificates
  else
    log "JDK 21 already present"
  fi
  local jh; jh="$(find_jdk21)"
  export JAVA_HOME="$jh" PATH="$jh/bin:$PATH"

  if [ ! -d "$GROBID_DIR" ]; then
    log "fetching GROBID ${GROBID_VERSION}"
    curl -fL --retry 3 -o "/opt/grobid-${GROBID_VERSION}.zip" \
      "https://github.com/kermitt2/grobid/archive/refs/tags/${GROBID_VERSION}.zip"
    unzip -q -o "/opt/grobid-${GROBID_VERSION}.zip" -d /opt
  else
    log "source tree already present at $GROBID_DIR"
  fi
  ln -sfn "$GROBID_DIR" /opt/grobid

  if [ ! -x "$LAUNCHER" ]; then
    # GROBID 0.9.1 ships Gradle 9.6.1, which refuses installDist because two resolved
    # dependencies contribute the same langdetect jar name and Gradle 9 dropped the
    # implicit duplicate strategy. An init script sets EXCLUDE without editing the
    # vendored source. installDist also refuses a non-empty partial install dir.
    cat >/opt/grobid-dup.gradle <<'EOF'
allprojects {
    tasks.withType(Copy).configureEach { duplicatesStrategy = DuplicatesStrategy.EXCLUDE }
    tasks.withType(Sync).configureEach { duplicatesStrategy = DuplicatesStrategy.EXCLUDE }
}
EOF
    log "building GROBID (this takes several minutes on a cold Gradle cache)"
    cd "$GROBID_DIR"
    ./gradlew clean install --no-daemon -x test
    rm -rf "${GROBID_DIR}/grobid-service/build/install"
    ./gradlew --init-script /opt/grobid-dup.gradle :grobid-service:installDist --no-daemon
  else
    log "launcher already built"
  fi
  configure
  write_unit
  log "install complete"
}

configure() {
  # Idempotent: each key is rewritten to the budgeted value every time.
  [ -f "${CONFIG}.orig" ] || cp "$CONFIG" "${CONFIG}.orig"
  sed -i \
    -e "s/^\( *memoryLimitMb:\) .*/\1 ${GROBID_PDFALTO_MB}/" \
    -e "s/^\( *concurrency:\) .*/\1 ${GROBID_CONCURRENCY}/" \
    "$CONFIG"
  # pdfalto's timeout is the FIRST timeoutSec under grobid.pdf.pdfalto; the later ones
  # belong to the consolidation services and are left alone.
  awk -v t="$GROBID_PDFALTO_TIMEOUT" '
    /pdfalto:/ {inp=1}
    inp && /timeoutSec:/ && !done {sub(/timeoutSec:.*/, "timeoutSec: " t); done=1}
    {print}' "$CONFIG" > "${CONFIG}.tmp" && mv "${CONFIG}.tmp" "$CONFIG"
  log "config: concurrency=${GROBID_CONCURRENCY} pdfaltoMB=${GROBID_PDFALTO_MB} pdfaltoTimeout=${GROBID_PDFALTO_TIMEOUT}s heap=${GROBID_HEAP_GB}g"
}

write_unit() {
  local jh; jh="$(find_jdk21)"
  cat >"$UNIT" <<EOF
[Unit]
Description=GROBID ${GROBID_VERSION} (CRF) service
After=network.target

[Service]
Type=simple
Environment=JAVA_HOME=${jh}
Environment=JAVA_OPTS=-Xmx${GROBID_HEAP_GB}g
WorkingDirectory=${GROBID_DIR}
ExecStart=${LAUNCHER} server ${CONFIG}
Restart=on-failure
RestartSec=5
# Dropwizard exits 143 (128+SIGTERM) on a clean shutdown, so without this a normal
# stop leaves the unit in state "failed" and status reports a healthy service as
# broken. 143 is a success here; a real crash still shows up.
# (No backticks in this heredoc: it is unquoted, so they would be executed.)
SuccessExitStatus=143
StandardOutput=append:/var/log/grobid.log
StandardError=append:/var/log/grobid.log

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  # Enabled so a distro boot brings the service back. This matters under WSL: when the
  # last wsl.exe session exits, WSL starts shutting the distro down and systemd stops
  # every unit (observed 2026-09-14 as status=143/SIGTERM while distro uptime kept
  # climbing, i.e. the shutdown was aborted by the next command but the units stayed
  # stopped). Callers should therefore run a whole batch inside ONE wsl.exe invocation,
  # beginning with `grobid.sh start` — which is idempotent and returns at once if alive.
  systemctl enable grobid >/dev/null 2>&1 || true
}

health() {
  curl -fsS --max-time 5 "http://localhost:${GROBID_PORT}/api/isalive" 2>/dev/null
}

do_start() {
  [ -x "$LAUNCHER" ] || { log "not installed; run: $0 install"; exit 1; }
  [ -f "$UNIT" ] || write_unit
  if [ "$(health || true)" = "true" ]; then log "already alive on ${GROBID_PORT}"; return 0; fi
  configure
  systemctl restart grobid
  local n=0
  while [ "$n" -lt 180 ]; do
    if [ "$(health || true)" = "true" ]; then log "alive after ${n}s"; return 0; fi
    sleep 2; n=$((n+2))
  done
  log "did not come alive within ${n}s; last 30 log lines:"; tail -30 /var/log/grobid.log
  return 1
}

do_stop() {
  systemctl stop grobid 2>/dev/null || true
  log "stopped"
}

do_status() {
  systemctl is-active grobid 2>/dev/null || true
  printf 'isalive: %s\n' "$(health || echo unreachable)"
}

case "${1:-status}" in
  install) do_install ;;
  configure) configure; write_unit ;;
  start) do_start ;;
  stop) do_stop ;;
  restart) do_stop; do_start ;;
  status) do_status ;;
  health) health; echo ;;
  *) echo "usage: $0 install|configure|start|stop|restart|status|health"; exit 2 ;;
esac
