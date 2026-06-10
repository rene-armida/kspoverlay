# kspoverlay

Twitch, etc., stream overlay graphics via HTML / CSS
Local data collection for KSP, sent by ksptelemetrymod

# concepts

Telemetry data is modeled as an Update. Each Update contains two bits of
potentially-identifying info: the Vessel Name and Sphere of Influence.
Matchers use these to associate the Update with a Mission. Missions are
long-lived, and can cross multiple vessels and SOIs. Telemetry data
is stored in the Mission object and then displayed on screen.

# arch

Python / Flask / sqlite / Gunicorn backend for REST API
ksptelemetrymod sends HTTP requests to the backend
