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
# The service is NOT set to autostart (see write_unit); `start` is idempotent and costs
# ~20-30 s cold. `enable`/`disable` toggle autostart if you want it.
#
# Resource budget (litkb decision litkb-p0-foundation §15.16: local workers keep 20% of RAM
# and CPU free for Kam). Host: 12 logical threads, 31 GiB visible to WSL.
#
# MEASURED 2026-09-14 (referee, 15 requests / 2,361 pages per pool size, cgroup + /proc
# sampling at 2 Hz). These are measurements, not the arithmetic they replaced:
#
#   pool | wall    | pages/s | peak service RSS | max one pdfalto | peak whole-system CPU
#      1 | 305.6 s |    7.73 |        8,243 MiB |        20.3 MiB |  58.6 %
#      4 | 116.9 s |   20.2  |       11,655 MiB |        20.5 MiB |  76.5 %
#      9 | 111.9 s |   21.1  |       13,758 MiB |        20.5 MiB | 100.0 %
#
#   * The JVM is NOT its heap. With -Xmx8g the service reached 8,243 MiB at pool 1 and
#     13,758 MiB at pool 9 — about 5.7 GiB of non-heap on top of the heap, rising ~689 MiB
#     per added worker. There is ONE JVM for the whole pool, so there is no per-worker
#     process and no per-worker RSS to measure; 689 MiB/worker is a derived slope.
#   * pdfalto never exceeded 20.5 MiB. The old budget's 1.5 GiB per worker was wrong by ~75x.
#     The cap below is left at 1536 MB as a ceiling, but it is NOT a budget term.
#   * RAM at pool 9 (13.84 GiB) does fit 24.8 GiB. CPU does NOT: pool 9 reached 100% non-idle
#     and left Kam nothing, which is exactly what the 20% rule forbids. Pool 4 peaks at 76.5%
#     and delivers 96% of pool 9's rate on this workload.
#
#   => GROBID_CONCURRENCY defaults to 4. Above 4 the script REFUSES unless
#      GROBID_BREAK_HEADROOM=1 is set, which says in the refusal that it breaks §15.16.
#
# Base note: WSL sees 31 of the host's 63.76 GiB but all 12 logical CPUs, so the two terms of
# §15.16 are not computed on the same base (RAM conservative, CPU not).
set -euo pipefail

GROBID_VERSION="${GROBID_VERSION:-0.9.1}"
GROBID_DIR="${GROBID_DIR:-/opt/grobid-${GROBID_VERSION}}"
GROBID_PORT="${GROBID_PORT:-8070}"
GROBID_HEAP_GB="${GROBID_HEAP_GB:-8}"
GROBID_CONCURRENCY="${GROBID_CONCURRENCY:-4}"
GROBID_HEADROOM_MAX_CONCURRENCY="${GROBID_HEADROOM_MAX_CONCURRENCY:-4}"
GROBID_BREAK_HEADROOM="${GROBID_BREAK_HEADROOM:-0}"
GROBID_PDFALTO_MB="${GROBID_PDFALTO_MB:-1536}"
GROBID_PDFALTO_TIMEOUT="${GROBID_PDFALTO_TIMEOUT:-300}"
GROBID_JDK="${GROBID_JDK:-}"
# Where JDKs are looked for. Overridable so the "no JDK 21 anywhere" refusal can be tested
# without uninstalling one.
GROBID_JVM_DIR="${GROBID_JVM_DIR:-/usr/lib/jvm}"
UNIT=/etc/systemd/system/grobid.service
LAUNCHER="${GROBID_DIR}/grobid-service/build/install/grobid-service/bin/grobid-service"
CONFIG="${GROBID_DIR}/grobid-home/config/grobid.yaml"

log() { printf '[grobid.sh] %s\n' "$*"; }

find_jdk21() {
  if [ -n "$GROBID_JDK" ]; then printf '%s' "$GROBID_JDK"; return; fi
  ls -d "${GROBID_JVM_DIR}"/java-21-openjdk* 2>/dev/null | head -1
}

# GROBID 0.9.1 is compiled to class file version 65 and needs a JDK 21+. The refusal that
# existed before this was really an INVALID-DIRECTORY refusal: with JAVA_HOME unset the
# launcher silently fell back to `java` on PATH, which on a host with a 17 on PATH dies with
# an UnsupportedClassVersionError halfway through boot and on a host with a 21 quietly starts
# something we never chose (referee, 2026-09-14 §5). So the version is checked HERE, against
# the JDK this script will actually export, and an unresolvable or too-old JDK is a refusal —
# never a fall-back to PATH.
require_jdk21() {
  local jh; jh="$(find_jdk21 || true)"
  if [ -z "$jh" ]; then
    log "REFUSING: no JDK 21 found (looked at \$GROBID_JDK and ${GROBID_JVM_DIR}/java-21-openjdk*)."
    log "  GROBID 0.9.1 needs 21+; falling back to \`java\` on PATH is NOT allowed here."
    return 1
  fi
  if [ ! -x "$jh/bin/java" ]; then
    log "REFUSING: JAVA_HOME candidate '$jh' has no executable bin/java."
    return 1
  fi
  local ver major
  ver="$("$jh/bin/java" -version 2>&1 | head -1 | sed -n 's/.*version "\([0-9][0-9.]*\).*/\1/p')"
  major="${ver%%.*}"
  if [ -z "$major" ] || [ "$major" -lt 21 ] 2>/dev/null; then
    log "REFUSING: '$jh' is java ${ver:-unknown}; GROBID 0.9.1 requires 21 or newer."
    return 1
  fi
  log "JDK ok: $jh (java $ver)"
  printf '%s' "$jh" >/dev/null
  return 0
}

require_concurrency_headroom() {
  if [ "$GROBID_CONCURRENCY" -gt "$GROBID_HEADROOM_MAX_CONCURRENCY" ] && \
     [ "$GROBID_BREAK_HEADROOM" != "1" ]; then
    log "REFUSING concurrency=${GROBID_CONCURRENCY}: above ${GROBID_HEADROOM_MAX_CONCURRENCY} this"
    log "  BREAKS the 20% CPU-headroom rule (decisions.yaml litkb-p0-foundation §15.16)."
    log "  Measured 2026-09-14: pool 9 peaks at 100% whole-system CPU and leaves Kam nothing,"
    log "  while pool 4 peaks at 76.5% and gives 96% of pool 9's rate on the hard-paper set."
    log "  Set GROBID_BREAK_HEADROOM=1 to override, knowingly."
    return 1
  fi
  return 0
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
  require_jdk21 || exit 1
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
  # NOT enabled by default, deliberately. Under WSL the distro boots whenever anything
  # touches it, and an enabled unit would then start an 8 GiB-heap JVM unbidden and leave
  # it idle — the resource cost the 20%-headroom rule (decisions.yaml 15.16) exists to
  # avoid. `start` is idempotent and brings the service up cold in about 20-30 s, which is
  # cheap enough that autostart buys nothing.
  #
  # The lifecycle fact that makes this worth spelling out: when the last wsl.exe client
  # exits, WSL begins shutting the distro down and systemd stops every unit (observed
  # 2026-09-14 as status=143/SIGTERM while the distro's own uptime kept climbing — the
  # shutdown was aborted by the next command, but the units stayed stopped). So a caller
  # must either run a whole batch inside ONE wsl.exe invocation beginning with
  # `grobid.sh start`, or hold the distro open (the Python adapter's start() does that).
  #
  # `grobid.sh enable` turns autostart on for anyone who does want it.
  :
}

health() {
  curl -fsS --max-time 5 "http://localhost:${GROBID_PORT}/api/isalive" 2>/dev/null
}

do_start() {
  require_jdk21 || exit 1
  require_concurrency_headroom || exit 1
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
  check-jdk) require_jdk21 ;;
  check-concurrency) require_concurrency_headroom ;;
  configure) configure; write_unit ;;
  enable) write_unit; systemctl enable grobid; log "autostart on" ;;
  disable) systemctl disable grobid 2>/dev/null; log "autostart off" ;;
  start) do_start ;;
  stop) do_stop ;;
  restart) do_stop; do_start ;;
  status) do_status ;;
  health) health; echo ;;
  *) echo "usage: $0 install|check-jdk|check-concurrency|enable|disable|configure|start|stop|restart|status|health"; exit 2 ;;
esac
