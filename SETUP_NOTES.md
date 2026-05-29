# Foundry Dashboard Setup: go.ana.ng

## Overview
The Foundry dashboard is now running on `go.ana.ng` subdomain via Tailscale with the following architecture:

```
Tailscale Client → DNS (100.100.100.100) → go.ana.ng (100.116.31.73)
                                         → Nginx Reverse Proxy → Foundry App (port 8100)
```

---

## Components

### 1. DNS Resolution (Tailscale)
- **DNS Server**: `100.100.100.100` (Tailscale)
- **Resolution**: `go.ana.ng` → `127.0.0.1` (via Tailscale)
- **Access**: Only available from Tailscale network
- **Status**: Automatic via Tailscale

### 2. Reverse Proxy (nginx)
- **Configuration**: `/etc/nginx/conf.d/go.ana.ng.conf`
- **Listen**: `100.116.31.73:80` (Tailscale IP only)
- **ACL**: Only allows Tailscale CGNAT range `100.64.0.0/10`
- **Status**: Running via `systemctl`
- **Reload**: `systemctl reload nginx`

### 3. Foundry Dashboard Application
- **Location**: `/root/projects/foundry`
- **Port**: 8100 (localhost only, proxied via nginx)
- **Launch Command**: `python3 -m uvicorn foundry.dashboard.app:app --host 0.0.0.0 --port 8100`
- **Service**: `foundry-dashboard.service` (systemd)
- **Status**: Running via `systemctl`
- **Command**: `systemctl status foundry-dashboard`
- **Enable on Boot**: Already enabled

---

## Access

### From Tailscale Network
- **URL**: `http://go.ana.ng` (resolves to 100.116.31.73 via Tailscale DNS)
- **Direct IP**: `http://100.116.31.73`

### Local Access (no Tailscale)
- **Direct**: `http://localhost:8100`

### Test Commands
```bash
# Health check via Tailscale
curl http://go.ana.ng/health

# DNS resolution
nslookup go.ana.ng

# View dashboard (from Tailscale)
curl -I http://go.ana.ng/

# Direct local test
curl http://127.0.0.1:8100/
```

---

## Management

### View Logs
```bash
# Foundry application
journalctl -u foundry-dashboard -f

# Nginx
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# Dnsmasq
journalctl -u dnsmasq -f
```

### Restart Services
```bash
# Foundry app
systemctl restart foundry-dashboard

# Nginx
systemctl reload nginx

# Dnsmasq (requires restart, not reload)
systemctl restart dnsmasq
```

---

## Configuration Files

### Nginx: `/etc/nginx/conf.d/go.ana.ng.conf`
```nginx
server {
    listen 100.116.31.73:80;
    server_name go.ana.ng;

    allow 100.64.0.0/10;
    deny  all;

    access_log /var/log/nginx/go.ana.ng.access.log;
    error_log  /var/log/nginx/go.ana.ng.error.log;

    location / {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

### Systemd: `/etc/systemd/system/foundry-dashboard.service`
- Auto-restarts on failure
- Runs as root user
- Environment variables passed from system

---

## Troubleshooting

### DNS not resolving from Tailscale?
- Use `nslookup go.ana.ng` on a connected Tailscale client
- Ensure you're connected to the Tailscale network

### Nginx not proxying?
```bash
nginx -t  # Test config
systemctl reload nginx
tail -f /var/log/nginx/go.ana.ng.error.log
```

### Foundry app not responding?
```bash
systemctl status foundry-dashboard
journalctl -u foundry-dashboard -n 50
curl http://127.0.0.1:8100/health  # Direct test
```

### Port 8100 in use?
```bash
lsof -i :8100
```

### Can't access from non-Tailscale network?
- This setup is Tailscale-only by design (ACL: `100.64.0.0/10`)
- Access locally via `http://localhost:8100` instead

---

## Notes
- All services are enabled to start on system boot
- Application restarts automatically if it crashes
- Access is restricted to Tailscale network via nginx ACL
- Matches the `sys.ana.ng` pattern for consistency
- Logs available at `/var/log/nginx/go.ana.ng.*`
