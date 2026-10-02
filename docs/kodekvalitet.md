# Plan for bedre kodekvalitet

Tilbage til [README](../README.md) | Se også [Bidrag](../CONTRIBUTING.md)

Denne side beskriver en trinvis plan for produktionssikkerhed og bedre kodekvalitet
i MeterReplace. Produktionssikkerhed prioriteres før større refaktorering.
Planen dokumenterer kommende arbejde; den er ikke en godkendelse af den aktuelle
produktionsopsætning, som skal verificeres særskilt.

Planen er lavet efter en gennemgang af koden i september 2026, hvor appen kørte
med 37 testmetoder og 27 migrationsfiler. PR #71 rapporterer 37 grønne tests.

Status ved opdateringen den 18. september 2026:

- [PR #71: Ryd op i udgåede API'er og tilføj CI](https://github.com/Rmelin/MeterReplace/pull/71)
  er oprettet og fortsat åben; ændringerne er ikke en del af denne checkout
- PR'en erstatter `datetime.utcnow()` med `utc_now()` og `on_event` med `lifespan`.
  Tidshjælperen bevarer bevidst naive UTC-værdier, så databasens tidssemantik er uændret
- PR'en tilføjer CI med migrationer mod en tom database og `unittest` på
  Python 3.12 og 3.14. Trin 1 skal udvide denne CI, når PR'en er integreret
- `SECRET_KEY`-fallback er bevidst udskudt i PR #71
- nedenstående er resterende arbejde; testdækning findes allerede delvist

## Princip

En afgrænset ændring pr. pull request; et stort trin kan kræve flere PR'er. Refaktor-PR'er ændrer ikke funktionalitet, og
testsuiten skal være grøn både før og efter.

Trin 1 og de relevante tests fra trin 5 kommer før sammenlægning og opdeling af
logik i trin 2 og 4. Trin 3 kan gennemføres uafhængigt af service-opdelingen.
Adfærdsændringer, eksempelvis uploadgrænser og nye statusregler, får egne PR'er
med tydelige acceptkriterier frem for at indgå i ren refaktorering.

## Trin 1: Dev-værktøjer og lint

Problem: der er ingen linter, ingen formatter og ingen `requirements-dev.txt`.

Opgaver:

- opret `requirements-dev.txt` med `ruff`; behold `unittest` som testløber
  og tilføj kun `pytest`, hvis der er et konkret behov
- opret `pyproject.toml` med ruff-regler: `E`, `F`, `I`, `UP`, `B`
- kør `ruff check --fix` og `ruff format` i en separat commit, så diffen er læsbar
- tilføj `ruff check` og `ruff format --check` til CI fra PR #71, og behold
  migrations- og testkørslerne
- dokumentér ét virtuelt miljø (`.venv`) og installation af dev-afhængigheder

Værdi: ubrugte imports og variabler bliver fanget automatisk, og ensartet
formatering gør alle senere diffs mindre.

## Trin 2: Saml duplikeret logik

Problem: de samme hjælpefunktioner er kopieret mellem route-filer.

| Funktion | Antal kopier | Risiko |
|---|---|---|
| `latest_status_map` | 3 | Høj. Status kan vise forskelligt på dashboard og adresseliste |
| `parse_date` og `parse_time` | 5 og 5 | Lav, men støj |
| `ensure_image`, `save_photo`, `photo_complete` | 4, 3, 4 | Middel. Upload-validering bør være ens |
| `slugify_address` | 4 | Lav |
| `has_conflict`, `availability_for_user` | 3, 3 | Middel. Planlægningsregler bør være ét sted |

Opret `app/services/` med:

- `status.py` med `latest_status_map` som eneste sandhed
- `photos.py` med `ensure_image`, `save_photo`, `photo_complete` og `slugify_address`
- `forms.py` med `parse_date`, `parse_time`, `parse_datetime_local`
- `scheduling.py` med `has_conflict` og `availability_for_user`

Vigtigt: varianterne er ikke ens i dag. Planlægningens `latest_status_map`
mangler både `NOT_SCHEDULED`-fallback og `register_closed`-overstyring fra adresse-
og statusvisningen. Importens `parse_date` returnerer `datetime`, mens andre
varianter returnerer `date`.

Skriv tests af den eksisterende adfærd **før** kopierne fjernes. Dæk tomme input,
flere aftaler pr. adresse, statusprioritet og registerlukkede adresser samt
parsernes returtyper og ugyldige input. Afklar hvilke forskelle der er tilsigtede;
bevar dem eksplicit, eller ret dem i en særskilt adfærdsændring. En fælles helper
må ikke stiltiende ændre reglerne for planlægning.

## Trin 3: Én måde at rendere templates på

Problem: 33 kald til `TemplateResponse` bygger context manuelt, og 29 af dem
gentager de samme nøgler (`request`, `current_user`, `flashes`).

Opgave: lav en helper i `app/dependencies.py`:

```python
render(request, "side.html", user, **ctx)
```

Helperen tilføjer altid `request`, `current_user` og `flashes` og skal understøtte
`status_code` og `headers`. Bevar især fejlstatusser samt `Cache-Control` og
`Referrer-Policy` på beboerfejlsider. Test også at flash-beskeder kun forbruges én gang.

Værdi: fjerner omkring 100 linjer og gør det umuligt at glemme flash-beskeder
på en side.

## Trin 4: Split de store route-filer

Problem: routes, forretningslogik og queries er blandet i de samme filer.

| Fil | Linjer |
|---|---|
| `app/routes/admin_addresses.py` | 1629 |
| `app/routes/vvs_tasks.py` | 1126 |
| `app/routes/admin_appointments.py` | 1079 |
| `app/routes/admin_planning.py` | 973 |

Fremgangsmåde, én fil ad gangen:

1. flyt funktioner der ændrer data til `app/services/`
2. service-funktioner tager `db` og simple værdier, aldrig `Request`
3. route-funktionen bliver: læs formular, kald service, flash og redirect
4. flyt og udvid de eksisterende tests til service-funktionerne; behold relevante HTTP-tests
5. fastlæg én transaktionsgrænse pr. handling: aftaleændringer og lagerbevægelser
   skal committes samlet, og underliggende helpers må ikke committe delresultater
6. test rollback ved fejl samt oprydning af nye uploadfiler, hvis databasen ikke gemmes

Start med `admin_addresses.py`, fordi statuslogikken derfra bruges af andre dele.

## Trin 5: Testdækning der matcher risikoen

Der findes 37 testmetoder, blandt andet for push-beskeder, planlægningsslots,
beboer-selvbetjening, admin-statusovergange, VVS-afslutning og supportindstillinger.
Der er også tests af manuel planlægningscommit og visning af PDF-links; det er
ikke det samme som dækning af auto-planlægning eller selve PDF-genereringen.

Prioriterede huller:

- statusprioritet på tværs af visninger og flere aftaler på samme adresse
- commit af auto-planlægning, lagerbevægelser og gentagne indsendelser
- importflows, herunder ugyldige rækker og fejl under lagring
- selve brevgenereringen
- HTTP-adgangskontrol for login, roller og adgang til andre brugeres opgaver

Opgaver:

- tilføj `httpx` til dev-afhængigheder og lav en fælles testbase med `TestClient`,
  isoleret testdatabase og brugere med forskellige roller. Både request- og
  startup-kode skal bruge testdatabasen, aldrig den lokale driftsdatabase
- prioritér statusovergange først. Tabellen i [Statusmodel](status-model.md)
  er udgangspunkt for testcases, suppleret med lager- og øvrige sideeffekter
- dernæst importflows og commit af planlægning
- hver fejlrettelse fremover får en regressionstest

## Trin 6: Produktionssikkerhed — højeste prioritet

Nummereringen er bevaret, men dette trin påbegyndes først sammen med relevante
adgangskontroltests fra trin 5. PR #71 udskød `SECRET_KEY`; det tages nu op som
prioriteret opfølgning. Opdel arbejdet i små PR'er med følgende acceptkriterier:

### Opstart, sessions og admin-konto

- definér en eksplicit produktionsindstilling. Opstart i produktion skal afvise
  manglende, tom eller kendt udviklingsnøgle; dokumentér generering og rotation
  af en tilfældig `SECRET_KEY` uden at logge nøglen
- kræv sikre sessionscookies i produktion og verificér `Secure`, `HttpOnly` og
  eksplicit `SameSite=Lax` i HTTP-tests. Dokumentér HTTPS og proxyopsætning
- erstat automatisk oprettelse af `admin`/`admin123` i produktion med en eksplicit,
  sikker førstegangsopsætning. Beskriv overgangen for eksisterende installationer
- test både afvist usikker produktionskonfiguration og fungerende lokal udvikling

### Formularer og adgangskontrol

- tilføj CSRF-beskyttelse til tilstandsændrende sessionbaserede requests, inklusive
  formularer og JavaScript-kald. Test manglende, forkert og gyldigt token;
  `SameSite` alene er ikke acceptkriteriet
- test login, alle roller og ejerskab af opgaver via HTTP. Forkert rolle eller
  adgang til en anden brugers opgave må ikke ændre data
- gennemgå beboerlinks særskilt: verificér adgangens omfang, ugyldige links og
  at tokens ikke eksponeres i logs eller fejlbeskeder

### Uploads og misbrugsbeskyttelse

- gennemgå den nuværende offentlige `/upload`-mount. Beskyt private fotos med
  adgangskontrollerede downloads; dokumentér hvilke filer der eventuelt må være
  offentlige. Test anonyme brugere, forkerte roller og autoriserede downloads
- indfør maksimal uploadstørrelse og valider faktisk filindhold og tilladte
  formater frem for kun klientens MIME-type. Test afvisninger, fejlbeskeder og
  oprydning af delvist gemte filer. Dette må ikke vente på hele trin 2
- indfør rate limiting på login og `POST /r/{token}`. Vælg grænser ud fra reelle
  brugerflows og beskriv håndtering på tværs af workers og betroede proxyer.
  Test både legitime gentagelser og afvisning ved overskridelse

### Verificering af drift

- dokumentér og verificér HTTPS, filrettigheder, hemmeligheder, beskyttede backups
  og en faktisk gendannelsestest i et isoleret miljø
- tilføj automatiseret kontrol af kendte sårbarheder i Python-afhængigheder samt
  en procedure for at vurdere, rette og dokumentere fund
- opdatér [Sikkerhed](security.md) og [Drift og deployment](deployment.md) sammen
  med implementeringen. Registrér for hvert krav: gennemført ændring, testbevis
  og eventuelt resterende arbejde i produktionsmiljøet

Trinnet er først færdigt, når kravene er implementeret og verificeret. En grøn
unit-testsuite alene dokumenterer ikke produktionssikkerhed.

## Trin 7: Ryd op i småting

- fjern den ubrugte `year`-global i `app/main.py`, hvis ingen template bruger den
- konvertér `docs/forbedringsplan.html` til markdown som de øvrige sider, og
  opdatér den, da punktet om notifikationer er gennemført

Lokal vedligeholdelse holdes uden for kodekvalitets-PR'er: gennemgå mergede
branches før sletning, og håndtér databasekopier efter en særskilt backupplan med
opbevaring og verificeret gendannelse.

## Rækkefølge

| Trin | Estimat | Afhænger af |
|---|---|---|
| 1. Dev-værktøjer og lint | ½ dag | PR #71 for CI-udvidelsen |
| 2. Saml duplikeret logik | 1 til 2 dage | 1 og relevante tests fra 5 |
| 3. Render-helper | ½ dag | 1 |
| 4. Split route-filer | 2 til 3 dage, fordelt på flere PR'er | 2 og relevante tests fra 5 |
| 5. Testdækning | start før 2 og 4, fortsæt løbende | ingen |
| 6. Produktionssikkerhed | estimeres pr. del-PR | start først med relevante tests fra 5 |
| 7. Småting | ½ dag | ingen |

Estimaterne er foreløbige. Start med produktionssikkerhed i trin 6 og tilhørende
tests fra trin 5. Trin 1 kan gennemføres sideløbende. Fortsæt derefter med trin 2
og 4, når de relevante regressionstests er på plads. Trin 3 og 7 kan tages separat.

Statuslogikken i trin 2 er en væsentlig refaktoreringsrisiko, fordi varianterne
allerede er forskellige. Sikkerhedsarbejdet og verificering af drift har dog
højere prioritet end at fjerne duplikering.

## Relaterede sider

- [Bidrag](../CONTRIBUTING.md)
- [Statusmodel](status-model.md)
- [Sikkerhed](security.md)
