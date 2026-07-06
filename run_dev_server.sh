#!/bin/bash
PORT=8000
LOCAL_IP="$(ipconfig getifaddr en0)"
open "http://$LOCAL_IP:$PORT"
flask --app kspoverlay run --debug --host "$LOCAL_IP" -p "$PORT"
