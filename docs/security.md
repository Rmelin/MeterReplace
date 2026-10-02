# Sikkerhed

Tilbage til [README](../README.md) | Se også [Drift og deployment](deployment.md)

## Produktionsindstillinger

Produktion skal køre med `APP_ENV=production`. Appen afviser ved opstart:

- manglende, kort eller kendt udviklingsværdi i `SECRET_KEY`
- manglende `SESSION_COOKIE_SECURE=true`
- `PUBLIC_BASE_URL` uden et gyldigt HTTPS-domæne eller med sti/loginoplysninger
- manglende administrator eller en administrator med adgangskoden `admin123`

En længdekontrol beviser ikke, at en nøgle er tilfældig. Generér derfor nøglen:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Gem den i serverens beskyttede miljøfil. Genbrug nøglen ved normale deploys;
rotation logger alle ud. Nøglen må ikke deles mellem miljøer eller logges.
`PUBLIC_BASE_URL` er offentlig og skal matche serverens domæne. Andre Host-headere
afvises i produktion, også på health checks.

Uden `APP_ENV` bruges `development`, hvor lokal HTTP og udviklingsnøglen stadig
virker. Dette er ikke en produktionsindstilling. Ukendte miljønavne afvises.
En `.env`-fil indlæses ikke automatisk af appen; systemd indlæser den via
`EnvironmentFile`, som beskrevet i deployment-guiden.

## Første administrator og eksisterende installationer

Kør migrationerne og opret derefter den første administrator interaktivt:

```bash
python -m alembic upgrade head
python -m app.bootstrap_admin
```

Adgangskoden indtastes skjult og skal være mindst 16 tegn. Kommandoen nægter at
oprette en ekstra administrator, hvis der allerede findes en. Nye og ændrede
adgangskoder i brugeradministrationen kræver også mindst 16 tegn i produktion.
Eksisterende hashes ændres ikke automatisk.

På en eksisterende installation skal en eventuel standard-adminadgangskode
ændres i brugeradministrationen **før** produktionsindstillingen aktiveres.
Der oprettes ingen standardkonto i produktion. Lokal udvikling bevarer den
hidtidige førstegangsoprettelse af `admin`/`admin123` på en tom database.

## Sessions, formularer og roller

Sessionscookies bruger `HttpOnly`, eksplicit `SameSite=Lax` og i produktion
`Secure`. HTTPS skal håndhæves ved reverse proxyen. Appen sender HSTS i
produktion samt `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` og
`Referrer-Policy: no-referrer`. Dynamiske svar må ikke caches.

Alle tilstandsændrende HTTP-metoder kræver et CSRF-token fra sessionen. HTML-forms
sender `csrf_token`, og JSON-kald sender `X-CSRF-Token`. Login og logout rydder
sessionen, så gamle formularer skal genindlæses. Manglende eller forkert token
giver HTTP 403. PDF-downloads, som markerer aftaler som informeret, kræver nu
en bekræftelse via POST; et GET-link ændrer ikke længere denne status.

Eksisterende roller bevares: `admin` administrerer brugere og indstillinger,
`user` har de eksisterende kontorfunktioner, og `vvs` arbejder på egne opgaver.
`user` er således ikke en ren læsebruger. HTTP-tests kontrollerer rolle- og
opgaveadgang samt afvisning uden dataændringer.

## Private fotos og uploads

`/upload` er en adgangskontrolleret route, ikke en offentlig statisk mappe.

- `admin` og `user` kan hente fotos og logoer registreret i databasen
- `vvs` kan hente fotos knyttet til egne opgaver
- anonyme brugere henvises til login; andre uautoriserede opslag giver 404
- filer uden en matchende databasepost og stier uden for uploadmappen afvises

Reverse proxy eller CDN må **ikke** servere `data/uploads` direkte eller cache
`/upload`. Eksisterende billeder beholder deres stier. Ældre ikke-rasterformater
serveres som vedhæftede filer med en restriktiv sandbox-politik.

Nye billeder må højst være 10 MiB og 25 millioner pixels. Kun gyldigt JPEG, PNG
eller WebP accepteres efter kontrol af indholdet; MIME-type og filnavn er ikke
bevis. Billeder omkodes til JPEG eller PNG med tilfældige filnavne og uden
metadata. PNG bruges når transparens skal bevares. SVG og HEIC accepteres ikke;
konvertér dem til et understøttet format først. Den samlede requestgrænse er
12 MiB, også for CSV-importer og requests uden Content-Length. Fejl under lagring
ruller databasetransaktionen tilbage og fjerner den nye billedfil.

## Rate limiting og beboerlinks

Login tillader højst 10 forsøg pr. brugernavn og 30 pr. IP på 15 minutter.
Beboerformularer tillader 60 indsendelser pr. token og 120 pr. IP i timen.
Grænserne gælder også mislykkede forsøg med et gyldigt CSRF-token. Overskridelser
giver HTTP 429 med `Retry-After`; utilgængelig tællerdatabase giver 503.

Tællere gemmes atomisk i `data/security/rate-limits.db`, deles mellem workers på
samme server og overlever procesgenstart. Identiteter gemmes som HMAC-værdier,
ikke som beboertokens, brugernavne eller IP-adresser. Udløbne poster ryddes op.
Flere servere kræver fælles rate limiting ved proxyen eller en delt tællertjeneste;
SQLite-filen må ikke placeres på et netværksdrev.

Appen bruger klient-IP fra ASGI-serveren. Proxyen skal overskrive klientens
forwarded-headere, og Uvicorn må kun stole på den konkrete proxyadresse. Sæt ikke
`--forwarded-allow-ips='*'`. Begræns direkte adgang til appens port.

Beboerlinks giver adgang til den tilknyttede adresse og aftale uden login og skal
behandles som hemmelige adgangslinks. Inaktive og ukendte links afvises.
Undlad fulde requeststier i proxyens logs for `/r/`, og kør Uvicorn med
`--no-access-log`. Referrer- og cache-headere reducerer yderligere eksponering.

## Afhængigheder og kontroller

CI kører migrationer på en tom database, regressionstests og HTTP-sikkerhedstests
på Python 3.12 og 3.14. `pip-audit` kontrollerer produktionsafhængigheder ved PR,
push og ugentligt. Lokalt kan kontrollen køres med:

```bash
python -m pip install -r requirements-dev.txt pip-audit==2.9.0
python -m unittest discover -s tests -v
python -m pip_audit -r requirements.txt --strict
```

Ved fund: vurder den berørte kode, opdatér til en rettet kompatibel version og
kør tests, inklusive PDF-generering ved ændringer i PDF-biblioteker. Skjul ikke
fund med generelle undtagelser. En eventuel midlertidig undtagelse kræver en
konkret begrundelse, ansvarlig og dato for revurdering.

## Kontroller på produktionsserveren

Kode og tests verificerer ikke serverens opsætning. Før deploy skal følgende
kontrolleres og resultatet noteres:

1. produktionsmiljø, sessionsnøgle, HTTPS-domæne og sikre cookies
2. eksisterende adminadgangskode og behov for førstegangsopsætning
3. proxyens adgang til appen, betroede headere, uploadgrænse og ingen offentlig uploadmappe
4. ingen tokens i adgangslogs; ingen `.env`, database eller uploads i Git
5. dedikeret driftbruger og begrænset adgang til miljøfil, data og backups
6. konsistent backup af database og uploads samt vellykket gendannelse på en isoleret installation
7. login, formularer, mobilfotos, PDF-breve og beboerlinks efter deploy

Backups og eksporter indeholder persondata. Beskyt dem, fastlæg opbevaring og
sletning, og lad dem aldrig ligge under et offentligt webroot. Der er ikke kørt
ændringer eller en gendannelsestest på produktionsserveren som del af denne kodeændring.
