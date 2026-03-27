# 💧 Vandmålerudskiftning
Open source webapplikation til planlægning, udførsel og dokumentation af udskiftning af vandmålere.
Projektet er målrettet vandværker og forsyninger, som ønsker et simpelt, selvhostet system til styring af adresser, VVS-arbejde, beboerinformation og lager

## 🎯 Formål
- At understøtte hele processen omkring vandmålerudskiftning:
- Planlægning af udskiftninger
- Information af beboere/kunder
- Udførsel af VVS-arbejde
- Dokumentation med fotos
- Afslutning og overblik
- Simpel lagerstyring

Alt samlet i én webapp.

## ✨ Funktioner

### Admin
- Import og administration af adresser
- Auto-planlægning med preview (udkast) før commit
- Drag-and-drop planlægningsrækkefølge
- Statusdashboard med filtre og genveje
- Håndtering af unavailable-perioder pr. adresse
- Generering af PDF-breve til beboere/kunder
- Automatisk statusændring ved brev og foto
- Lagerstyring af vandmålere (inkl. justeringer)
- Inline redigering af aftaler og opgaver
- Overblik over historik (fx ikke hjemme)

### VVS
- Overblik over fremtidige arbejdsdage
- Se hvilke adresser der skal udføres hvornår
- Inline opdatering af opgaver
- Upload af billeder (gammel / ny måler)
- Foto-upload sætter automatisk status til Skiftet

## 🧱 Teknologi
**Backend**: FastAPI
**Templates**: Jinja2
Database: SQLite (kan udskiftes)
Frontend: Server-renderet HTML + CSS
Tema: Dark / Light mode + accent-farver
PDF: Server-side generering

Bevidst valgt for:
- Lav kompleksitet
- Let drift
- Nem tilpasning

## 🚀 Kom i gang
```bash
git clone https://github.com/Rmelin/MeterReplace.git
cd MeterReplace

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0
```

## 🔄 Opdatering (git pull)

### Lokal udvikling
```bash
git pull
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0
```

### Produktion (systemd)
```bash
cd /opt/meterreplace
sudo -u meterreplace git pull
sudo -u meterreplace /opt/meterreplace/.venv/bin/pip install -r /opt/meterreplace/requirements.txt
sudo systemctl restart meterreplace
```

## Åbn:

👉 http://localhost:8000
eller 
http://IP:8000

## 🚢 Deployment

### systemd (Debian/Ubuntu)
Nedenfor er et simpelt produktions-setup med `uvicorn` direkte via systemd.

#### 1) Opret systembruger og mappe
```bash
sudo useradd -r -s /usr/sbin/nologin meterreplace
sudo mkdir -p /opt/meterreplace
sudo chown -R meterreplace:meterreplace /opt/meterreplace
```

#### 2) Læg kode i /opt og opsæt venv
```bash
sudo -u meterreplace git clone https://github.com/Rmelin/MeterReplace.git /opt/meterreplace
sudo -u meterreplace python -m venv /opt/meterreplace/.venv
sudo -u meterreplace /opt/meterreplace/.venv/bin/pip install -r /opt/meterreplace/requirements.txt
```

#### 3) Opret miljøvariabler
Opret `/opt/meterreplace/.env` og udfyld mindst:
```bash
PUBLIC_BASE_URL=http://DIT_DOMAENE
```

#### 4) systemd service
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

#### 5) Aktiver og start
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now meterreplace
sudo systemctl status meterreplace
```

#### 6) Logs
```bash
journalctl -u meterreplace -f
```

## 🧭 Overordnet proces
Adresser oprettes/importeres
Vandmålertype og lager oprettes
VVS-brugere oprettes med arbejdstider
Admin planlægger adresser (preview → commit)
PDF-breve genereres → status Beboer/kunde informeret
VVS udfører arbejde og uploader fotos → status Skiftet
Sagen afsluttes → status Afsluttet

## 📊 Statusflow
Systemet arbejder med følgende statusser:
UNPLANNED – Ikke planlagt
PLANNED – Planlagt
INFORMED – Beboer/kunde informeret (brev sendt)
COMPLETED – Skiftet (foto uploadet)
CLOSED – Afsluttet
NOT_HOME – Ikke hjemme (nuværende)
NOT_HOME_HISTORY – Ikke hjemme (historik)
NEEDS_RESCHEDULE – Behov for ny dato
Statusser bruges konsekvent i:
Dashboard
Filtre
Adresseoversigt
Historik

### 📅 Auto-planlægning
Planlægning sker i udkast
Intet gemmes før Commit
Rækkefølgen styrer tidslommer
Adresser kan omrokeres
Unavailable-perioder respekteres
“Hoppet over” bruges kun som buffer (fx målerbrønd)

### 📦 Lagerstyring
Lager kan justeres manuelt
Kun fratræk (forbrug)
Note er påkrævet
Lager må gerne gå i minus
Alle bevægelser logges som Justering

### 📄 Breve & PDF
PDF genereres server-side
Base URL styres via PUBLIC_BASE_URL
Beboerlink/QR kan slås fra globalt
Når PDF genereres, sættes status automatisk til INFORMED
Preview matcher endeligt output

### 🎨 UI & Tema
Dark / Light mode
Valgbar accent-farve
Farver kan adskilles pr. rolle

#### Standardfarver:
- Admin: Grøn #22c55e
- VVS: Blå #4da3ff
- Default: Orange #f97316


🤝 Bidrag Bidrag er meget velkomne:
Bug reports
Feature-forslag
Pull requests
Dokumentation
Principper:
Simpelt > smart
Læsbart > magisk
Tydelige flows
Opret gerne et issue før større ændringer.

### 📦 Produktion & ansvar
Projektet er designet til selvhosting.
Der ydes ingen garanti for drift, datasikkerhed eller compliance.
Brug sker på eget ansvar.
