# Plan for bedre kodekvalitet

Tilbage til [README](../README.md) | Se også [Bidrag](../CONTRIBUTING.md)

Denne side beskriver en trinvis plan for at forbedre kodekvaliteten i MeterReplace.

Planen er lavet efter en gennemgang af koden i september 2026, hvor appen kørte
stabilt med 37 grønne tests og 28 migrationer.

Status ved planens start:

- udgåede API'er (`datetime.utcnow`, `on_event`) er ryddet op, og CI er tilføjet
  i en separat oprydnings-PR
- trin 1 til 7 herunder er ikke påbegyndt

## Princip

Et trin pr. pull request. Refaktor-PR'er ændrer ikke funktionalitet, og
testsuiten skal være grøn både før og efter.

Trin 1 til 3 er fundamentet. De gør de større ændringer i trin 4 sikre at lave.

## Trin 1: Dev-værktøjer og lint

Problem: der er ingen linter, ingen formatter og ingen `requirements-dev.txt`.

Opgaver:

- opret `requirements-dev.txt` med `ruff` og `pytest`
- opret `pyproject.toml` med ruff-regler: `E`, `F`, `I`, `UP`, `B`
- kør `ruff check --fix` og `ruff format` i en separat commit, så diffen er læsbar
- tilføj `ruff check` som trin i CI
- ryd op i de to virtuelle miljøer, så README og den faktiske sti passer sammen

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
- `photos.py` med `ensure_image`, `save_photo`, `photo_complete` og en maksimal filstørrelse
- `forms.py` med `parse_date`, `parse_time`, `parse_datetime_local`
- `scheduling.py` med `has_conflict` og `availability_for_user`

Vigtigt: skriv en test pr. service-funktion **før** kopierne fjernes. Så beviser
testen, at de tre `latest_status_map`-varianter faktisk opfører sig ens, eller
afslører at de ikke gør.

## Trin 3: Én måde at rendere templates på

Problem: 33 kald til `TemplateResponse` bygger context manuelt, og 29 af dem
gentager de samme nøgler (`request`, `current_user`, `flashes`).

Opgave: lav en helper i `app/dependencies.py`:

```python
render(request, "side.html", user, **ctx)
```

Helperen tilføjer altid `request`, `current_user` og `flashes`.

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
4. skriv tests mod service-funktionerne, hvilket ikke kræver HTTP

Start med `admin_addresses.py`, fordi statuslogikken derfra bruges af andre dele.

## Trin 5: Testdækning der matcher risikoen

I dag er der 37 tests, primært på push-beskeder, planlægningsslots og
beboer-selvbetjening.

Ikke dækket:

- statusovergange i admin
- commit af auto-planlægning
- importflows
- brevgenerering

Opgaver:

- tilføj `httpx` til dev-afhængigheder og lav en fælles testbase med `TestClient`,
  database i hukommelsen og en logget-ind admin
- prioritér statusovergange først. Tabellen i [Statusmodel](status-model.md)
  fungerer som en færdig testliste
- dernæst importflows og commit af planlægning
- hver fejlrettelse fremover får en regressionstest

## Trin 6: Mindre sikkerhedsforbedringer

- `SECRET_KEY`: appen bør nægte at starte uden en rigtig nøgle i produktion
- sæt `same_site="lax"` eksplicit på `SessionMiddleware`. Det er standard i dag,
  men bør være synligt i koden
- maksimal filstørrelse ved upload. Kommer naturligt med trin 2
- simpel rate limit på `POST /r/{token}`, for eksempel højst fem svar pr. token i timen

Se [Sikkerhed](security.md) for de øvrige sikkerhedsnoter.

## Trin 7: Ryd op i småting

- slet lokale branches der allerede er merget:
  `git branch --merged main | grep -v main | xargs git branch -d`
- fjern den ubrugte `year`-global i `app/main.py`, hvis ingen template bruger den
- ryd op i de mange kopier af databasefilen i `data/data/`. Lav en `backups/`-mappe
  med datostemplede filer eller et backup-script
- konvertér `docs/forbedringsplan.html` til markdown som de øvrige sider, og
  opdatér den, da punktet om notifikationer er gennemført

## Rækkefølge

| Trin | Estimat | Afhænger af |
|---|---|---|
| 1. Dev-værktøjer og lint | ½ dag | ingen |
| 2. Saml duplikeret logik | 1 dag | 1 |
| 3. Render-helper | ½ dag | 1 |
| 4. Split route-filer | 2 til 3 dage | 2 og 3 |
| 5. Testdækning | løbende | 2 |
| 6. Sikkerhed | ½ dag | ingen |
| 7. Småting | ½ dag | ingen |

Trin 1, 6 og 7 kan tages uafhængigt af de andre.

Den største reelle risiko ligger i trin 2, fordi `latest_status_map` findes i tre
kopier og bruges til at vise status i flere skærmbilleder.

## Relaterede sider

- [Bidrag](../CONTRIBUTING.md)
- [Statusmodel](status-model.md)
- [Sikkerhed](security.md)
