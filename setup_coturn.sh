#!/usr/bin/env bash
# Install and configure coturn on the VPS (Ubuntu/Debian). Run as root.
#   sudo TURN_USER=lt TURN_PASS='something-long' bash setup_coturn.sh
# If TURN_PASS is unset a random one is generated and printed at the end.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)"; exit 1; }

TURN_USER="${TURN_USER:-lt}"
TURN_PASS="${TURN_PASS:-$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)}"
PORT="${TURN_PORT:-3478}"
MIN_PORT="${RELAY_MIN:-49152}"
MAX_PORT="${RELAY_MAX:-49252}"          # 100 relay ports = plenty for a few sessions
REALM="${TURN_REALM:-turn.local}"

# Public IP and the IP actually bound on this box (differ on OCI/AWS-style 1:1 NAT)
PUBLIC_IP="${PUBLIC_IP:-$(curl -s4 --max-time 8 https://api.ipify.org || true)}"
PRIVATE_IP="${PRIVATE_IP:-$(ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')}"
[ -n "$PUBLIC_IP" ] || { echo "could not detect public IP; rerun with PUBLIC_IP=x.x.x.x"; exit 1; }

apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y coturn curl

# Debian/Ubuntu packages ship coturn disabled by default
if [ -f /etc/default/coturn ]; then
  sed -i 's/^#\?TURNSERVER_ENABLED=.*/TURNSERVER_ENABLED=1/' /etc/default/coturn
  grep -q TURNSERVER_ENABLED /etc/default/coturn || echo 'TURNSERVER_ENABLED=1' >> /etc/default/coturn
fi

EXTERNAL="$PUBLIC_IP"
[ "$PRIVATE_IP" != "$PUBLIC_IP" ] && EXTERNAL="$PUBLIC_IP/$PRIVATE_IP"

cat > /etc/turnserver.conf <<EOF
listening-port=$PORT
listening-ip=$PRIVATE_IP
external-ip=$EXTERNAL
min-port=$MIN_PORT
max-port=$MAX_PORT
realm=$REALM
lt-cred-mech
user=$TURN_USER:$TURN_PASS
fingerprint
no-cli
no-tls
no-dtls
no-multicast-peers
# keep relays from reaching the VPS's own private network / metadata service
denied-peer-ip=10.0.0.0-10.255.255.255
denied-peer-ip=172.16.0.0-172.31.255.255
denied-peer-ip=192.168.0.0-192.168.255.255
denied-peer-ip=169.254.0.0-169.254.255.255
denied-peer-ip=127.0.0.0-127.255.255.255
# allow our own public relay address as a peer (client<->client relaying on this box)
allowed-peer-ip=$PRIVATE_IP
allowed-peer-ip=$PUBLIC_IP
log-file=/var/log/turnserver.log
simple-log
EOF

# --- host firewall (OCI Ubuntu images ship iptables rules that REJECT everything else) ---
open_ipt() {
  # insert before any REJECT rule: idempotent via -C check
  iptables -C INPUT "$@" 2>/dev/null || iptables -I INPUT 1 "$@"
}
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow $PORT/udp; ufw allow $PORT/tcp; ufw allow $MIN_PORT:$MAX_PORT/udp
else
  open_ipt -p udp --dport $PORT -j ACCEPT
  open_ipt -p tcp --dport $PORT -j ACCEPT
  open_ipt -p udp --dport $MIN_PORT:$MAX_PORT -j ACCEPT
  command -v netfilter-persistent >/dev/null && netfilter-persistent save || \
    echo "NOTE: iptables rules are not persisted (install iptables-persistent)"
fi

systemctl enable coturn
systemctl restart coturn
sleep 1
systemctl --no-pager --lines=5 status coturn || true

cat <<EOF

================ coturn ready ================
TURN host:port : $PUBLIC_IP:$PORT
username       : $TURN_USER
password       : $TURN_PASS
relay ports    : UDP $MIN_PORT-$MAX_PORT

!! Also open in the cloud console (OCI: VCN > Security List / NSG ingress):
   UDP+TCP $PORT, UDP $MIN_PORT-$MAX_PORT, source 0.0.0.0/0
   The host firewall alone is not enough.

Test (from your laptop, needs the 'coturn' package or use the browser test):
   https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/
   -> add  turn:$PUBLIC_IP:$PORT  with the user/pass above, Gather candidates,
   you must see at least one candidate of type "relay".
==============================================
EOF
