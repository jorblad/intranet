#!/bin/sh
set -e

# Generate a tiny runtime config that the SPA will load before other scripts.
# If BACKEND_URL is set, expose it as window.__API_PROXY_TARGET__ and API_BASE.
cat > /usr/share/nginx/html/runtime-config.js <<EOF
(function () {
  try {
    var b = "${BACKEND_URL:-}";
    if (b && b !== "") {
      window.__API_PROXY_TARGET__ = b;
      window.__APP_CONFIG__ = { API_BASE: b };
    }
  } catch (e) {}
})();
EOF

exec "$@"
