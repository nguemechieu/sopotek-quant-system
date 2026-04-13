#!/bin/sh
set -eu

export DISPLAY="${DISPLAY:-:99}"
export SOPOTEK_HTTP_UI="${SOPOTEK_HTTP_UI:-1}"
export SOPOTEK_DISABLE_WEBENGINE="${SOPOTEK_DISABLE_WEBENGINE:-1}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export QTWEBENGINE_DISABLE_SANDBOX="${QTWEBENGINE_DISABLE_SANDBOX:-1}"
export QTWEBENGINE_CHROMIUM_FLAGS="${QTWEBENGINE_CHROMIUM_FLAGS:---no-sandbox --disable-gpu --disable-gpu-compositing --disable-gpu-rasterization --disable-dev-shm-usage --disable-features=Vulkan,VulkanFromANGLE,UseSkiaRenderer}"
export LIBGL_ALWAYS_SOFTWARE="${LIBGL_ALWAYS_SOFTWARE:-1}"
export QT_OPENGL="${QT_OPENGL:-software}"
export QT_QUICK_BACKEND="${QT_QUICK_BACKEND:-software}"
export QSG_RHI_BACKEND="${QSG_RHI_BACKEND:-software}"
export QT_XCB_GL_INTEGRATION="${QT_XCB_GL_INTEGRATION:-none}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-sopotek}"
export SCREEN_WIDTH="${SCREEN_WIDTH:-1600}"
export SCREEN_HEIGHT="${SCREEN_HEIGHT:-900}"
export SCREEN_DEPTH="${SCREEN_DEPTH:-24}"
export VNC_PORT="${VNC_PORT:-5900}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"
export NOVNC_RESIZE_MODE="${NOVNC_RESIZE_MODE:-off}"
export NOVNC_RECONNECT="${NOVNC_RECONNECT:-1}"
export NOVNC_SHOW_DOT="${NOVNC_SHOW_DOT:-1}"
export NOVNC_WEB_ROOT="${NOVNC_WEB_ROOT:-/usr/share/novnc}"
export NOVNC_TEMPLATE_PATH="${NOVNC_TEMPLATE_PATH:-/app/scripts/docker/novnc/index.html}"
export NOVNC_TLS_ENABLED="${NOVNC_TLS_ENABLED:-0}"
export NOVNC_TLS_HOSTNAME="${NOVNC_TLS_HOSTNAME:-localhost}"
export NOVNC_TLS_CERT_PATH="${NOVNC_TLS_CERT_PATH:-/app/output/novnc/selfsigned.crt}"
export NOVNC_TLS_KEY_PATH="${NOVNC_TLS_KEY_PATH:-/app/output/novnc/selfsigned.key}"
export NOVNC_TLS_CERT_DAYS="${NOVNC_TLS_CERT_DAYS:-30}"
export X11VNC_EXTRA_ARGS="${X11VNC_EXTRA_ARGS:-}"

mkdir -p "$XDG_RUNTIME_DIR" /app/logs
chmod 700 "$XDG_RUNTIME_DIR"

Xvfb "$DISPLAY" -screen 0 "${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}" -ac +extension GLX +render -noreset >/app/logs/xvfb.log 2>&1 &
XVFB_PID=$!

DISPLAY_SOCKET="/tmp/.X11-unix/X${DISPLAY#:}"
READY=0
for _ in $(seq 1 40); do
    if [ -e "$DISPLAY_SOCKET" ]; then
        READY=1
        break
    fi
    sleep 0.25
done

if [ "$READY" -ne 1 ]; then
    echo "Timed out waiting for Xvfb display $DISPLAY" >&2
    exit 1
fi

fluxbox >/app/logs/fluxbox.log 2>&1 &
FLUXBOX_PID=$!

autocutsel -display "$DISPLAY" >/app/logs/autocutsel-clipboard.log 2>&1 &
AUTOCUTSEL_CLIPBOARD_PID=$!

autocutsel -display "$DISPLAY" -selection PRIMARY >/app/logs/autocutsel-primary.log 2>&1 &
AUTOCUTSEL_PRIMARY_PID=$!

x11vnc -display "$DISPLAY" -rfbport "$VNC_PORT" -forever -shared -nopw -quiet $X11VNC_EXTRA_ARGS >/app/logs/x11vnc.log 2>&1 &
X11VNC_PID=$!

NOVNC_ENCRYPT_FLAG="0"
NOVNC_SCHEME="http"
if [ "$NOVNC_TLS_ENABLED" = "1" ]; then
    NOVNC_ENCRYPT_FLAG="1"
    NOVNC_SCHEME="https"
    mkdir -p "$(dirname "$NOVNC_TLS_CERT_PATH")"
    if [ ! -s "$NOVNC_TLS_CERT_PATH" ] || [ ! -s "$NOVNC_TLS_KEY_PATH" ]; then
        openssl req -x509 -nodes -newkey rsa:2048 \
            -days "$NOVNC_TLS_CERT_DAYS" \
            -keyout "$NOVNC_TLS_KEY_PATH" \
            -out "$NOVNC_TLS_CERT_PATH" \
            -subj "/CN=${NOVNC_TLS_HOSTNAME}" >/app/logs/novnc-cert.log 2>&1
    fi
fi

if [ -f "$NOVNC_TEMPLATE_PATH" ]; then
    sed \
        -e "s/__NOVNC_RESIZE__/${NOVNC_RESIZE_MODE}/g" \
        -e "s/__NOVNC_ENCRYPT__/${NOVNC_ENCRYPT_FLAG}/g" \
        -e "s/__NOVNC_RECONNECT__/${NOVNC_RECONNECT}/g" \
        -e "s/__NOVNC_SHOW_DOT__/${NOVNC_SHOW_DOT}/g" \
        "$NOVNC_TEMPLATE_PATH" > "${NOVNC_WEB_ROOT}/index.html"
fi

if [ "$NOVNC_TLS_ENABLED" = "1" ]; then
    websockify \
        --web "$NOVNC_WEB_ROOT" \
        --cert "$NOVNC_TLS_CERT_PATH" \
        --key "$NOVNC_TLS_KEY_PATH" \
        --ssl-only \
        "$NOVNC_PORT" \
        "localhost:${VNC_PORT}" >/app/logs/novnc.log 2>&1 &
else
    websockify \
        --web "$NOVNC_WEB_ROOT" \
        "$NOVNC_PORT" \
        "localhost:${VNC_PORT}" >/app/logs/novnc.log 2>&1 &
fi
NOVNC_PID=$!

cleanup() {
    kill "$NOVNC_PID" "$X11VNC_PID" "$AUTOCUTSEL_PRIMARY_PID" "$AUTOCUTSEL_CLIPBOARD_PID" "$FLUXBOX_PID" "$XVFB_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

printf '%s\n' "Browser UI available at ${NOVNC_SCHEME}://localhost:${NOVNC_PORT}/"
printf '%s\n' "Direct noVNC URL: ${NOVNC_SCHEME}://localhost:${NOVNC_PORT}/vnc.html?autoconnect=1&reconnect=${NOVNC_RECONNECT}&resize=${NOVNC_RESIZE_MODE}&show_dot=${NOVNC_SHOW_DOT}&encrypt=${NOVNC_ENCRYPT_FLAG}"
if [ "$NOVNC_RESIZE_MODE" = "off" ]; then
    printf '%s\n' "Browser scrolling is enabled for the full desktop view. Set NOVNC_RESIZE_MODE=scale if you prefer fit-to-window scaling."
fi
if [ "$NOVNC_TLS_ENABLED" = "1" ]; then
    printf '%s\n' "TLS is enabled for noVNC. If a self-signed certificate was generated, trust the browser warning once before reconnecting."
fi
printf '%s\n' "Clipboard bridge enabled. If your browser blocks Ctrl+V, use the noVNC clipboard panel to paste text into the app."

python -m sopotek_trading "$@"
