#!/bin/sh
set -eu

api_origin="${VITE_API_ORIGIN:-}"
escaped_origin=$(printf '%s' "$api_origin" | sed 's/\\/\\\\/g; s/"/\\"/g')

cat > /usr/share/nginx/html/runtime-config.js <<EOF
window.__SCALERAG_CONFIG__ = {
  API_ORIGIN: "$escaped_origin"
};
EOF

exec nginx -g "daemon off;"
