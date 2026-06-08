#!/bin/bash
PORT=5051
open "http://localhost:$PORT"
flask --app kspoverlay run --debug --host "192.168.0.211" -p "$PORT"
