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

Opret en `.env`-fil med de relevante værdier:

```env
SECRET_KEY=skift-denne-til-en-lang-tilfaeldig-vaerdi
PUBLIC_BASE_URL=https://dit-domaene
SESSION_COOKIE_SECURE=true
VAPID_PRIVATE_KEY=/opt/meterreplace/secrets/vapid-private.pem
VAPID_PUBLIC_KEY=indsæt-den-offentlige-nøgle
VAPID_SUBJECT=mailto:drift@example.dk
```

| Variabel | Påkrævet | Beskrivelse |
|---|---|---|
| `SECRET_KEY` | Ja | Bruges af sessions middleware |
| `PUBLIC_BASE_URL` | Anbefalet | Bruges i links og PDF-breve |
| `SESSION_COOKIE_SECURE` | Ja i produktion | Sæt til `true`, når appen kører over HTTPS |
| `VAPID_PRIVATE_KEY` | Ved Web Push | Sti til den private VAPID PEM-fil |
| `VAPID_PUBLIC_KEY` | Ved Web Push | Offentlig VAPID-nøgle til browseren |
| `VAPID_SUBJECT` | Ved Web Push | Kontaktadresse, fx `mailto:drift@example.dk` |

Hvis `PUBLIC_BASE_URL` ikke er sat, bruges requestens base URL som fallback.

## VAPID-nøgler til Web Push

Web Push bruger et VAPID-nøglepar til at identificere MeterReplace over for
Apple og andre push-tjenester. Nøgleparret består af:

- en offentlig nøgle, som sendes til browseren ved oprettelse af et abonnement
- en privat nøgle, som serveren bruger til at signere push-anmodninger

Nøgleparret skal genereres én gang og derefter genbruges. Hvis privatnøglen
udskiftes, registrerer indstillingssiden det gamle abonnement og beder hver
telefon om at aktivere notifikationer igen.

### Generér nøgleparret

Kør dette på produktionsserveren efter installation af projektets dependencies:

```bash
sudo install -d -m 700 -o meterreplace -g meterreplace /opt/meterreplace/secrets
cd /opt/meterreplace
sudo -u meterreplace /opt/meterreplace/.venv/bin/python - <<'PY'
import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

private_key = ec.generate_private_key(ec.SECP256R1())
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
private_path = Path("/opt/meterreplace/secrets/vapid-private.pem")
private_path.write_bytes(private_pem)
private_path.chmod(0o600)

public_key = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.X962,
    format=serialization.PublicFormat.UncompressedPoint,
)
print(base64.urlsafe_b64encode(public_key).rstrip(b"=").decode("ascii"))
PY
```

Kommandoen gemmer privatnøglen i
`/opt/meterreplace/secrets/vapid-private.pem` og udskriver den offentlige nøgle.
Den offentlige nøgle er ikke hemmelig og må sendes til browseren.

Kør ikke kommandoen igen ved almindelige deployments. Tag en krypteret backup
af privatnøglen, og begræns adgangen til systembrugeren `meterreplace`.

### Konfigurér miljøvariablerne

Tilføj følgende til `/opt/meterreplace/.env`:

```env
VAPID_PRIVATE_KEY=/opt/meterreplace/secrets/vapid-private.pem
VAPID_PUBLIC_KEY=indsæt-den-offentlige-nøgle-fra-kommandoen
VAPID_SUBJECT=mailto:drift@example.dk
```

`VAPID_PRIVATE_KEY` indeholder filstien i stedet for selve PEM-teksten.
`pywebpush` kan læse nøglen direkte fra filen, og løsningen undgår en skrøbelig
multiline-hemmelighed i systemd-miljøfilen. Privatnøglen må aldrig placeres i
Git, databasen, logs eller sendes til browseren. `.gitignore` udelukker allerede
filer med endelserne `.pem` og `.key`.

`VAPID_SUBJECT` er kontaktoplysningen i de signerede push-anmodninger. Brug en
aktiv driftsmailadresse. Genstart applikationen og push-workeren efter ændring
af miljøvariablerne.

## Lokal udvikling

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
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
cd /opt/meterreplace
sudo -u meterreplace /opt/meterreplace/.venv/bin/python -m alembic upgrade head
```

### 3. Opret miljøfil

Generér først VAPID-nøgleparret som beskrevet ovenfor. Opret derefter
`/opt/meterreplace/.env`:

```env
SECRET_KEY=skift-denne-til-en-lang-tilfaeldig-vaerdi
PUBLIC_BASE_URL=https://dit-domaene
SESSION_COOKIE_SECURE=true
VAPID_PRIVATE_KEY=/opt/meterreplace/secrets/vapid-private.pem
VAPID_PUBLIC_KEY=indsæt-den-offentlige-nøgle
VAPID_SUBJECT=mailto:drift@example.dk
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

### 5. Opret Web Push-worker

Push-leveringer ligger i databasen, indtil en worker sender dem. Opret
`/etc/systemd/system/meterreplace-push.service`:

```ini
[Unit]
Description=Send MeterReplace Web Push notifications
After=network-online.target

[Service]
Type=oneshot
User=meterreplace
Group=meterreplace
WorkingDirectory=/opt/meterreplace
EnvironmentFile=/opt/meterreplace/.env
ExecStart=/opt/meterreplace/.venv/bin/python -m app.push_worker
```

Opret derefter `/etc/systemd/system/meterreplace-push.timer`:

```ini
[Unit]
Description=Run MeterReplace Web Push worker every minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
Persistent=true

[Install]
WantedBy=timers.target
```

Workerens leveringskø genprøver midlertidige fejl. Kør kun én worker ad gangen,
da standarddatabasen er SQLite. Serveren skal kunne oprette udgående
HTTPS-forbindelser til `*.push.apple.com`. Leveringen er "at least once": Et
processtop lige efter Apple har accepteret en push kan i sjældne tilfælde give
en dublet, men beskeden går ikke tabt af den grund.

### 6. Start services

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now meterreplace
sudo systemctl enable --now meterreplace-push.timer
sudo systemctl status meterreplace
sudo systemctl status meterreplace-push.timer
```

### 7. Se logs

```bash
journalctl -u meterreplace -f
journalctl -u meterreplace-push -f
```

## Reverse proxy

Typisk køres appen bag Nginx, Caddy eller Cloudflare.

Vigtigt i drift:

- appen serverer selv `/static`
- appen serverer selv `/upload`
- aggressiv cache på CSS og JS kan give gammelt UI efter deployment
- HTTPS skal håndhæves, gerne med HSTS
- port `8000` bør kun være tilgængelig fra reverse proxyen eller det interne net

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
sudo -u meterreplace /opt/meterreplace/.venv/bin/python -m alembic upgrade head
sudo systemctl restart meterreplace
```

Kør altid Alembic via appens `.venv` i produktion. Brug ikke `python3 -m alembic ...`, da den kan bruge systemets globale pakker i stedet for projektets dependencies. Se også [Fejlsøgning: Alembic og database er ude af sync](troubleshooting.md#alembic-og-database-er-ude-af-sync).

## Verifikation efter deploy

Efter deploy bør du kontrollere:

1. at login-siden loader
2. at admin kan logge ind
3. at `/admin/status` og `/admin/addresses` virker
4. at CSS og JavaScript er opdateret
5. at uploads og PDF-generering stadig virker
6. at `python -m alembic current` viser revision `0026`
7. at `meterreplace-push.timer` er aktiv
8. at notifikationer kan aktiveres fra den installerede app på en fysisk iPhone
9. at en ny beboerbesked opretter en levering og viser en notifikation

## Kendte driftsfælder

- gammel `styles.css` kan blive serveret fra cache
- lokal database og produktionsdatabase er to forskellige filer
- hvis `SECRET_KEY` skifter mellem deploys, bliver aktive sessioner ugyldige
- hvis `PUBLIC_BASE_URL` er forkert, bliver links og QR-koder i breve forkerte
