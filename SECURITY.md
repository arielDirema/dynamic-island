# Security Policy

## Reporting a vulnerability

Please report security issues privately through the repository's GitHub Security Advisories rather
than opening a public issue. Include the affected version, a minimal reproduction and any relevant
Windows or Python version details.

## Local data model

Dynamic Island stores settings, API keys, clipboard history and the phone server certificate locally
under `%APPDATA%\DynamicIsland` (or the user-selected synchronization folder). These files are not
committed to the repository.

- GitHub and Binance credentials are stored in plain text in the local settings file. Use restricted,
  read-only keys and protect the Windows account and synchronization folder.
- The phone server listens on the local network with a secret token and a self-signed HTTPS certificate.
  It is intended for trusted private networks only.
- Do not attach local settings, certificates, clipboard data or unredacted logs to public reports.
