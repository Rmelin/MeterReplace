# Drift og deployment

Tilbage til [README](../README.md) | Se også [Fejlsøgning](troubleshooting.md)

Se også [Sikkerhed](security.md) for secrets, HTTPS og øvrige sikkerhedsnoter.

Denne side beskriver et simpelt produktionssetup for MeterReplace.

## Krav

- Linux-server, fx Debian eller Ubuntu
- Python installeret
- `git`
- systemd
- en reverse proxy eller direkte adgang til port `8000`

## Miljøvariabler

Opret en `.env`-fil med mindst:

```env
SECRET_KEY=skift-denne-til-en-lang-tilfaeldig-vaerdi
PUBLIC_BASE_URL=https://dit-domaene
```

| Variabel | Påkrævet | Beskrivelse |
|---|---|---|
| `SECRET_KEY` | Ja | Bruges af sessions middleware |
| `PUBLIC_BASE_URL` | Anbefalet | Bruges i links og PDF-breve |

Hvis `PUBLIC_BASE_URL` ikke er sat, bruges requestens base URL som fallback.

## Lokal udvikling

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```

## Produktion med systemd

### 1. Opret systembruger og mappe

```bash
sudo useradd -r -s /usr/sbin/nologin meterreplace
sudo mkdir -p /opt/meterreplace
sudo chown -R meterreplace:meterreplace /opt/meterreplace
```

### 2. Hent kode og installer dependencies

```bash
sudo -u meterreplace git clone https://github.com/Rmelin/MeterReplace.git /opt/meterreplace
sudo -u meterreplace python -m venv /opt/meterreplace/.venv
sudo -u meterreplace /opt/meterreplace/.venv/bin/pip install -r /opt/meterreplace/requirements.txt
```

### 3. Opret miljøfil

Opret `/opt/meterreplace/.env`:

```env
SECRET_KEY=skift-denne-til-en-lang-tilfaeldig-vaerdi
PUBLIC_BASE_URL=https://dit-domaene
```

### 4. Opret systemd service

Opret `/etc/systemd/system/meterreplace.service`:

```ini
[Unit]
Description=MeterReplace
After=network.target

[Service]
User=meterreplace
Group=meterreplace
WorkingDirectory=/opt/meterreplace
EnvironmentFile=/opt/meterreplace/.env
ExecStart=/opt/meterreplace/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 5. Start servicen

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now meterreplace
sudo systemctl status meterreplace
```

### 6. Se logs

```bash
journalctl -u meterreplace -f
```

## Reverse proxy

Typisk køres appen bag Nginx, Caddy eller Cloudflare.

Vigtigt i drift:

- appen serverer selv `/static`
- appen serverer selv `/upload`
- aggressiv cache på CSS og JS kan give gammelt UI efter deployment

Hvis du bruger CDN eller reverse proxy cache, bør du have en strategi for cache-busting eller cache purge ved release.

## Data og persistens

Standardplaceringer i den nuværende kode:

- database: `data/data/app.db`
- uploads: `data/uploads/`
- logs til register-import: `data/logs/`

Sikring i produktion:

- tag backup af `data/`
- behold `data/` ved deploys
- undgå at slette uploads eller SQLite-filen ved opdatering

## Opdatering af produktion

```bash
cd /opt/meterreplace
sudo -u meterreplace git pull
sudo -u meterreplace /opt/meterreplace/.venv/bin/pip install -r /opt/meterreplace/requirements.txt
sudo systemctl restart meterreplace
```

## Verifikation efter deploy

Efter deploy bør du kontrollere:

1. at login-siden loader
2. at admin kan logge ind
3. at `/admin/status` og `/admin/addresses` virker
4. at CSS og JavaScript er opdateret
5. at uploads og PDF-generering stadig virker

## Kendte driftsfælder

- gammel `styles.css` kan blive serveret fra cache
- lokal database og produktionsdatabase er to forskellige filer
- hvis `SECRET_KEY` skifter mellem deploys, bliver aktive sessioner ugyldige
- hvis `PUBLIC_BASE_URL` er forkert, bliver links og QR-koder i breve forkerte
