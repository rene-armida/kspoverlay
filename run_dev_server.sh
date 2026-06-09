#!/bin/bash
PORT=8000
open "http://localhost:$PORT"
flask --app kspoverlay run --debug --host "192.168.0.211" -p "$PORT"
