#!/usr/bin/env python3
"""Configure Nextcloud's trusted local TLS gateway."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import stack
for key,value in [('overwritehost','nextcloud.localhost:8443'),('overwriteprotocol','https'),('overwritecondaddr',r'^172\.30\.80\.2$')]:
 stack.occ('config:system:set',key,'--value='+value,capture_output=True)
stack.occ('config:system:set','trusted_domains','10','--value=nextcloud.localhost',capture_output=True)
stack.occ('config:system:set','trusted_proxies','10','--value=172.30.80.2',capture_output=True)
print('Nextcloud local HTTPS gateway configured')
