#!/bin/bash
systemctl stop whitelist-api.service
systemctl status whitelist-api.service --no-pager | grep "Active"
