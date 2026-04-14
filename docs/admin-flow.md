# Admin-flow

Tilbage til [README](../README.md) | Se også [Statusmodel](status-model.md)

Denne side beskriver de vigtigste admin-flows i den rækkefølge de typisk bruges.

## 1. Log ind

Admin logger ind via `/login` og lander derefter på `/admin/addresses`.

Vigtige admin-sider i navigationen:

- `/admin/status`
- `/admin/addresses`
- `/admin/addresses/map`
- `/admin/appointments`
- `/admin/planning`
- `/admin/availability`
- `/admin/letters/template`
- `/admin/messages`
- `/admin/inventory`
- `/admin/users`
- `/admin/street-priority`
- `/admin/import/completed`
- `/admin/import/register`
- `/admin/missing-photos`

## 2. Opret eller importer adresser

Admin arbejder normalt først med adresser.

Muligheder:

- opret adresser manuelt
- importer adresser via adresseimport
- rediger adresseoplysninger
- geokod koordinater til kortvisning
- upload fotos på adressen
- registrer unavailable-perioder

Adresseoversigten kan filtreres på status og bruges som den centrale driftsliste.

## 3. Opret arbejdsdage for VVS

Før planlægning skal der være arbejdsdage i systemet.

Det sker i `/admin/availability`.

Her opretter admin:

- VVS-bruger
- dato
- starttid
- sluttid
- eventuel note

Arbejdsdagene bruges senere af statusdashboardet og planlægningen.

## 4. Planlæg adresser automatisk

Auto-planlægning findes i `/admin/planning`.

Flowet er:

1. vælg en dato med eksisterende arbejdsdage
2. klik preview
3. gennemgå planlagte adresser og oversprungne adresser
4. juster eventuelt adresse-rækkefølge
5. commit planen

Vigtige regler:

- preview gemmer ikke noget i databasen
- commit opretter `SCHEDULED`-aftaler
- commit laver samtidig en lagerreservation
- unavailable-perioder respekteres
- blokerede adresser og buffer-adresser holdes ude af normal planlægning

## 5. Planlæg manuelt

Hvis auto-planlægning ikke er nok, kan admin bruge `/admin/planning/manual`.

Her vælger admin:

- dato
- adresse
- VVS-bruger
- starttid

Manuel planlægning er nyttig til undtagelser, ombookinger og enkelte restadresser.

## 6. Send breve og informer beboere

Breve styres fra `/admin/letters/template`.

Admin kan:

- redigere brevskabelon
- uploade logo
- slå beboerlink/QR til eller fra
- generere PDF for en enkelt adresse
- generere batch-PDF for planlagte adresser

Når brev genereres for en relevant aftale, bruges planlagt dato og tidsvindue i outputtet.

Breve er knyttet til planlagte og informerede aftaler og indgår i det samlede statusflow.

## 7. Behandl beboersvar og beskeder

Beboerlink peger på resident-flowet, men admin følger op fra `/admin/messages` og adresseoversigten.

Typiske resultater:

- beboer bekræfter tidspunkt
- beboer skriver besked
- beboer anmoder om ny dato

En anmodning om ny dato kan føre til status `NEEDS_RESCHEDULE`.

## 8. Følg op på opgaver

Admin kan se og redigere opgaver i `/admin/appointments`.

Her kan admin blandt andet:

- redigere opgaver inline
- oprette manuelle opgaver
- registrere meterdata
- uploade fotos
- afslutte sager

VVS har tilsvarende et separat arbejdsflow i `/vvs/tasks`.

## 9. Importer færdige eller afsluttede sager

Der findes to importflows:

### Import af skiftet

Route: `/admin/import/completed`

Bruges til at importere sager der er udført, inklusive dato, VVS-navn og eventuelle fotos.

Importen kan også:

- oprette manglende arbejdsdage for VVS
- importere foto-stier fra ZIP
- eksportere færdige sager som ZIP med `completed.csv`

### Import af afsluttet

Route: `/admin/import/register`

Bruges til at markere adresser som afsluttede ud fra registerdata og nyt måler-nummer.

Importen:

- opdaterer nyt måler-nummer på adressen
- sætter `register_closed = true`
- sætter seneste aftale til `CLOSED`, hvis den findes

## 10. Mangler fotos

Side: `/admin/missing-photos`

Denne side bruges til at finde adresser som ser færdige ud i drift, men mangler billeder.

Det er nyttigt som kvalitetssikring efter import eller VVS-arbejde.

## 11. Lager og brugere

Admin vedligeholder også:

- lager i `/admin/inventory`
- brugere i `/admin/users`
- vejprioritet i `/admin/street-priority`

Lageret påvirkes både af planlægning og manuelle justeringer.

## 12. Følg status på dashboardet

Dashboardet på `/admin/status` er adminens overblik.

Det bruges til at svare på:

- hvor mange adresser er planlagt eller informeret
- hvor mange er skiftet eller afsluttet
- hvor mange kræver ny dato
- hvor mange beskeder er kommet ind
- hvordan går det pr. arbejdsdag
- hvilke veje mangler stadig arbejde

Se [Statusmodel](status-model.md) for de præcise beregningsregler.
