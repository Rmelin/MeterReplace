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
git clone https://github.com/Rmelin/vandmalerudskiftning.git
cd vandmalerudskiftning

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0
```

## Åbn:

👉 http://localhost:8000
eller 
http://IP:8000

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
