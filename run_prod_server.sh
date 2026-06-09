#!/bin/bash

LOCAL_IP="$(ipconfig getifaddr en0)"
BIND="$LOCAL_IP:8000"

gunicorn -w 4 -b "$BIND" kspoverlay:app
