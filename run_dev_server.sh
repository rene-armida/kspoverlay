#!/bin/bash
PORT=8000
LOCAL_IP="$(ipconfig getifaddr en0)"
# open "http://$LOCAL_IP:$PORT"
KSPOVERLAY_CONF="config-dev.toml" \
    flask --app kspoverlay run --debug --host "$LOCAL_IP" -p "$PORT"
