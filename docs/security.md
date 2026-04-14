# Sikkerhed

Tilbage til [README](../README.md) | Se også [Drift og deployment](deployment.md)

Denne side samler de vigtigste sikkerhedsnoter for MeterReplace.

## Kort version

Hvis du kun gør fem ting i produktion, så gør dette:

1. sæt en stærk `SECRET_KEY`
2. skift standard-admin adgangskoden med det samme
3. brug altid HTTPS
4. commit aldrig `.env`, databasefiler eller uploads til Git
5. tag backup af `data/` og beskyt serveradgang

## Hvad bruges `SECRET_KEY` til?

`SECRET_KEY` bruges til appens sessions.

I den nuværende kode bruges den af `SessionMiddleware`, som holder styr på blandt andet:

- login-session
- `user_id` i sessionen
- flash-beskeder i UI

Hvis `SECRET_KEY` er svag eller kendt, bliver session-sikkerheden dårligere.

Vigtigt:

- `SECRET_KEY` er hemmelig og skal behandles som en rigtig secret
- `PUBLIC_BASE_URL` er ikke en secret
- hvis `SECRET_KEY` ændres, bliver eksisterende logins ugyldige

## Sådan genererer du en stærk `SECRET_KEY`

Den anbefalede metode er Python `secrets`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Det giver en stærk tilfældig nøgle, som er velegnet til sessions.

Alternativt kan du bruge OpenSSL:

```bash
openssl rand -hex 32
```

## Eksempel på `.env`

```env
SECRET_KEY=indsæt-en-lang-tilfældig-hemmelig-nøgle-her
PUBLIC_BASE_URL=https://dit-domaene
```

Anbefalinger:

- generér nøglen én gang pr. miljø
- brug ikke samme nøgle til alle servere, hvis miljøerne skal være adskilte
- behold samme nøgle ved normale deploys
- roter kun nøglen bevidst

## Standard admin-bruger

Hvis databasen er tom ved første opstart, opretter appen automatisk:

- brugernavn: `admin`
- adgangskode: `admin123`

Det er praktisk lokalt, men skal behandles som en midlertidig startkonto.

I produktion bør du:

1. logge ind straks efter første opstart
2. ændre adgangskoden med det samme
3. oprette de rigtige brugere under `/admin/users`
4. undgå at lade standard-login være aktivt i drift

## HTTPS

Kør altid produktion bag HTTPS.

Hvorfor:

- login-cookies må ikke sendes ukrypteret
- admin-sider, breve og beboerlinks bør ikke gå over almindelig HTTP
- brugere forventer et sikkert domæne

Praktisk anbefaling:

- brug Nginx, Caddy, Traefik eller Cloudflare foran appen
- omdirigér HTTP til HTTPS
- sørg for at det offentlige domæne matcher `PUBLIC_BASE_URL`

## Håndtering af `.env`, database og uploads

Følgende bør ikke i Git:

- `.env`
- `data/data/app.db`
- `data/uploads/`
- eksporter med persondata eller billeder

Det matcher allerede `.gitignore` i projektet.

Praktiske råd:

- gem `.env` kun på serveren
- begræns læseadgang til driftbrugeren og administratorer
- lad ikke backup-filer ligge offentligt tilgængeligt

## Adgangskoder og brugere

Appen gemmer ikke adgangskoder i klartekst. Der bruges password-hash i databasen.

I drift bør du stadig:

- bruge unikke, lange adgangskoder
- undgå at dele admin-kontoen mellem flere personer
- oprette separate brugere til admin, VVS og øvrige roller
- fjerne eller ændre konti, som ikke længere bruges

## Server- og filrettigheder

Giv kun den nødvendige adgang på serveren.

Anbefalinger:

- kør appen som en dedikeret systembruger
- giv kun skriveadgang hvor appen faktisk har behov
- beskyt mapper som `data/` og `.env` med fornuftige filrettigheder
- begræns SSH-adgang til de personer, der administrerer systemet

## Backup og persondata

Systemet kan indeholde følsomme data:

- adresser
- kundeoplysninger
- beskeder fra beboere
- fotos
- målernumre

Du bør derfor:

- tage regelmæssig backup af `data/`
- opbevare backup sikkert
- vide hvem der har adgang til backup
- slette testdata og gamle eksporter, når de ikke længere skal bruges

## OBS-punkter i den nuværende kodebase

Disse punkter er særligt vigtige at kende:

### 1. Fallback til `dev-secret`

Hvis `SECRET_KEY` ikke er sat, falder appen tilbage til værdien `dev-secret`.

Det er acceptabelt til lokal udvikling, men bør ikke bruges i produktion.

### 2. `PUBLIC_BASE_URL` er ikke hemmelig

`PUBLIC_BASE_URL` styrer links og PDF-breve, men er ikke en secret.

Den skal være korrekt, men ikke skjules på samme måde som `SECRET_KEY`.

### 3. Ingen synlig CSRF-beskyttelse

Den nuværende kodebase bruger sessions og POST-forms, men der er ikke synlig dedikeret CSRF-beskyttelse i appen.

Det betyder i praksis:

- produktion bør køre bag HTTPS
- admin-adgang bør være begrænset til betroede brugere
- det er værd at overveje CSRF-beskyttelse som en fremtidig forbedring

### 4. Statiske filer og cache

Hvis du bruger CDN eller proxy-cache, kan gamle statiske filer blive serveret efter deploy.

Det er ikke i sig selv et hemmelighedsproblem, men det kan gøre drift og fejlsøgning forvirrende.

## Tjekliste før produktion

1. `SECRET_KEY` er sat i `.env`
2. `PUBLIC_BASE_URL` peger på det rigtige HTTPS-domæne
3. standard admin-adgangskode er ændret
4. `.env`, database og uploads er ikke i Git
5. backup af `data/` er på plads
6. serveren er bag HTTPS
7. kun de nødvendige personer har adgang til server og admin-login

## Relaterede sider

- [Drift og deployment](deployment.md)
- [Fejlsøgning](troubleshooting.md)
- [Bidrag](../CONTRIBUTING.md)
