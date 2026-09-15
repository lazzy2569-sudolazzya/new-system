#!/usr/bin/env bash
# Wired to NUT's upsmon as a NOTIFYCMD (or apcupsd's doshutdown script) so a
# UPS running low on battery triggers a graceful stop *before* power cuts.
#
# A UPS alone does not prevent the unclean-shutdown corruption the plan
# warns about (section 1.2) if the outage outlasts the battery -- this
# closes that gap.
#
# Configure in /etc/nut/upsmon.conf on the app server:
#   NOTIFYCMD /path/to/battery-shutdown.sh
#   NOTIFYFLAG LOWBATT SYSLOG+EXEC+WALL

set -euo pipefail

if [[ "${NOTIFYTYPE:-}" == "LOWBATT" ]]; then
    logger "UPS reported LOWBATT: stopping PostgreSQL cleanly before shutdown"
    systemctl stop postgresql
    shutdown -h now "UPS battery critical, shutting down"
fi
