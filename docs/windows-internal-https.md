# Windows Server 2022: internal HTTPS with IIS

These are installation instructions, not a claim that your VM/DNS/certificate or
LAN connectivity has been configured or tested. The development environment is
Linux. Do not expose this service to the internet or add public NAT/port forwarding.

## Local default

`start.bat` uses Waitress at `127.0.0.1:8000`. Only loopback clients and explicit
localhost hostnames are accepted. Accounts and permissions are required even in
localhost mode. Bind/port/host/proxy configuration is read at startup:

| Variable | Default / use |
| --- | --- |
| CIRRUS_BIND | 127.0.0.1; Waitress listening address |
| CIRRUS_PORT | 8000; 1–65535 |
| CIRRUS_ALLOWED_HOSTS | localhost,127.0.0.1; exact comma-separated names/IPs, no schemes/ports/wildcards |
| CIRRUS_INTERNAL_ACCESS | 0; set 1 deliberately for authorized remote access |
| CIRRUS_HTTPS | 0 locally; set 1 behind IIS HTTPS (requires HTTPS requests, Secure cookies) |
| CIRRUS_TRUSTED_PROXY | unset; only 127.0.0.1 or ::1 may be configured |
| CIRRUS_ALLOW_HTTP_LAN | unset; explicit 1 permits plaintext LAN diagnostics if HTTPS is off |
| CIRRUS_DATA_DIR | existing data path; legacy JOSEPH_DATA_DIR also accepted |

Use a dedicated service account for Waitress, with read access to application code
and Modify access only to its data directory. Give ordinary users browser access,
not Windows/filesystem/database access. NTFS permissions on the data directory,
backups, logs and private keys must exclude ordinary users. Run manually first;
then configure your organization's approved Windows service wrapper or scheduled
startup task under that service account, using the same environment variables.
An interactive terminal closing stops a manually launched server.

## Values to decide with your network administrator

Record your actual VM private IPv4 address, internal DNS zone/FQDN, approved
client IP addresses/subnets, certificate authority, Waitress port and data path.
`workplace.example.internal` and C:\ paths in examples are placeholders to replace.
Do not assume those values describe your network. A VM IP belongs in DNS/firewall
configuration; the internal FQDN belongs in allowed hosts and certificate SANs.

## IIS and reverse proxy

1. Back up the instance and install the upgrade/accounts locally first.
2. On Server 2022, install IIS and management tools (elevated PowerShell):

   ```powershell
   Install-WindowsFeature Web-Server, Web-Mgmt-Tools -IncludeManagementTools
   ```

   Install Microsoft IIS **URL Rewrite** and **Application Request Routing (ARR)**
   from the official IIS/Microsoft distribution. Verify both modules in IIS Manager.
   No app cloud hosting, external database, or Docker is required.
3. Keep IIS Anonymous Authentication enabled for the proxy site; the application
   enforces its own account login. Do not treat IIS anonymous mode as anonymous app
   access or substitute unconfigured forwarded identity headers.
   In IIS Manager → server → Application Request Routing Cache → Server Proxy
   Settings, enable proxy. Configure **preserveHostHeader=true** for ARR at server
   level. The application validates the original HTTP Host; do not rewrite it to
   127.0.0.1. ARR/proxy settings can also be managed through IIS configuration:

   ```bat
   %windir%\system32\inetsrv\appcmd.exe set config -section:system.webServer/proxy /enabled:true /preserveHostHeader:true /commit:apphost
   ```

4. Create a dedicated physical proxy folder (for example C:\Sites\CirrusProxy)
   containing only `web.config`. Use `deployment/web.config.example`, replacing
   `__WAITRESS_PORT__` with your configured port. Do not place application source,
   SQLite, uploads, staging data or backups in an IIS-served folder.
5. Permit the site rule to set `HTTP_X_FORWARDED_PROTO` and
   `HTTP_X_FORWARDED_FOR` in URL Rewrite → View Server Variables at server level.
   The supplied rule overwrites them with `https` and the actual client address.
   Do not merely append or pass through values supplied by clients. Disable ARR's
   automatic client-IP append to this same header, if enabled: the application
   accepts exactly one validated client IP, not a comma-separated proxy chain.
   Verify the rewrite/ARR settings together on your installed module version.
6. Run the app with a customized copy of `deployment/internal.example.bat`.
   Keep Waitress bound to 127.0.0.1; set internal access, HTTPS, explicit FQDN and
   the local trusted proxy address. IIS communicates with localhost HTTP; the
   external browser connection is HTTPS. No firewall opening for Waitress's port
   is needed or wanted.
7. The app trusts only a single configured loopback proxy for protocol/client-IP
   headers. It never trusts X-Forwarded-Host/Port or arbitrary Forwarded headers.
   Direct remote clients cannot enable trusted headers by sending them. Local
   OS administrators/processes remain outside the application's trust boundary.

## DNS, certificates, and binding

1. Have the internal DNS administrator create an **A record** mapping the chosen
   internal FQDN to the VM's private IPv4 address. This is an internal zone record,
   not an external public host. If using Windows DNS, the administrator can use
   Add-DnsServerResourceRecordA with your actual zone/name/address. Confirm from
   each authorized client:

   ```powershell
   Resolve-DnsName YOUR_INTERNAL_FQDN
   ```

2. Obtain a Server Authentication certificate from your internal CA with the
   exact internal FQDN in its Subject Alternative Name, a valid date range and
   private key on the server. Bind it in IIS site → Bindings → **https**, port 443,
   correct interface/IP and hostname (SNI if needed). Keep only intended bindings.
3. Deploy the CA root/intermediate public certificates through GPO/MDM or your
   trusted administrator process to client trust stores. Verify the certificate
   fingerprint through your CA before importing it. Never distribute the server's
   private key to clients and never instruct users to ignore certificate warnings.
   A self-signed certificate is only appropriate for a controlled test where its
   identity/trust is explicitly installed and verified.
4. DNS naming alone does not enable HTTPS. IIS must have the certificate/private
   key and binding, and the client must trust the issuing chain. HTTPS to the VM
   IP usually fails hostname validation unless that exact IP is also in the SAN;
   use the configured FQDN.

## Windows Firewall and network boundary

Allow inbound TCP 443 only to the VM's internal interface and only from approved
laptop/colleague IPs or tightly controlled subnets. Use actual values, for example:

```powershell
$CirrusVmAddress = 'REPLACE_WITH_PRIVATE_IP'
$CirrusApprovedClients = @('REPLACE_WITH_APPROVED_IP_OR_CIDR')
New-NetFirewallRule -DisplayName 'Cirrus Workplace internal HTTPS' `
  -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $CirrusVmAddress `
  -LocalPort 443 -RemoteAddress $CirrusApprovedClients -Profile Domain,Private
```

Review existing broad IIS/443 allow rules: Windows allow rules combine, so a new
narrow rule does not cancel an existing broad allowance. Disable/narrow conflicting
rules through your network administrator. Do not open port 8000 to the LAN for
this IIS configuration. Restrict access at upstream firewalls/VLANs too; do not
forward the site from a public router. Protect IIS/application logs, which can
contain paths or search terms.

## HTTP IP/port versus internal HTTPS name

- `http://VM_IP:PORT` uses plaintext HTTP, has no server certificate or transport
  encryption, and requires explicit non-loopback binding/firewall/allowed IP host
  settings. It is not the recommended deployment. The app rejects LAN binding
  unless internal access and an explicit plaintext diagnostic override are set.
  Do not use real credentials/customer data for plaintext network diagnostics.
- `https://INTERNAL_FQDN` uses trusted TLS on IIS, validates the certificate against
  DNS name, and proxies locally to Waitress. Secure cookies and HTTPS enforcement
  require CIRRUS_HTTPS=1. Do not disable certificate or host verification to make a
  failed setup appear successful.

## Verification checklist on the VM/clients

Start Waitress with the internal configuration; verify its listener is localhost.
Open the FQDN from an approved laptop and inspect the certificate (no warnings).
Log in with an individual account; test role restrictions and a deliberately
unshared record URL. Test an unauthorized client is blocked by firewall/network.
Restart the app and verify data remains (sessions intentionally expire at restart).
Test file uploads/import size limits and a restore into a new directory. If IIS
returns 502, verify Waitress/port and ARR; 400 often indicates host/scheme mismatch;
403 can indicate network or role/permission policy. Do not relax protections as a
workaround—correct the configured name, proxy headers or access assignment.
