#!/bin/bash
PORT=5051
open "http://localhost:$PORT"
flask --app kspoverlay run --debug -p "$PORT"
