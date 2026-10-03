#!/bin/sh
# Keep this file on a USB drive; install the latest published wheel on this computer.
set -eu

if [ "$#" -ne 0 ]; then
    echo 'Usage: install-ventoy-library.sh' >&2
    exit 2
fi

ventoy_library_python=${VENTOY_LIBRARY_PYTHON:-python3}
if ! command -v "$ventoy_library_python" >/dev/null 2>&1; then
    echo 'Python 3.11 or newer is required.' >&2
    exit 1
fi

if ! "$ventoy_library_python" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    echo 'Python 3.11 or newer is required. Set VENTOY_LIBRARY_PYTHON to its executable.' >&2
    exit 1
fi

# pipx may itself run under an older Python; use the interpreter checked above.
PIPX_DEFAULT_PYTHON=$(command -v "$ventoy_library_python")
export PIPX_DEFAULT_PYTHON

exec "$ventoy_library_python" -c 'import urllib.request; exec(urllib.request.urlopen("https://numberformat.github.io/noami-installer/install.py").read())' ventoy-library
