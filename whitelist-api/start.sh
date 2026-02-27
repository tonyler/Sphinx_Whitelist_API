#!/bin/bash
systemctl start whitelist-api.service
systemctl status whitelist-api.service --no-pager | grep -E "Active|Main PID"
