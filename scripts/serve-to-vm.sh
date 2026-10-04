#!/usr/bin/env bash
# Serve the current directory to the Windows guest over the default libvirt NAT network.
# In Windows, open http://192.168.122.1:8000/ . Stop with Ctrl+C.
# The host firewall must allow inbound TCP 8000 on virbr0.
cd "$(dirname "$0")" && exec python3 -m http.server 8000 --bind 192.168.122.1
