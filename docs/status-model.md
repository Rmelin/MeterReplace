# Statusmodel

Tilbage til [README](../README.md) | Se også [Admin-flow](admin-flow.md)

Denne side beskriver de statusser og afledte tællinger systemet bruger.

## Faktiske statusser i systemet

| Status | Betydning |
|---|---|
| `NOT_SCHEDULED` | Adressen er ikke planlagt |
| `SCHEDULED` | Adressen er planlagt |
| `INFORMED` | Beboer/kunde er informeret |
| `COMPLETED` | Arbejdet er udført/skiftet |
| `CLOSED` | Sagen er afsluttet |
| `NOT_HOME` | Beboer var ikke hjemme |
| `NEEDS_RESCHEDULE` | Der er behov for ny dato |

## Vigtige afgrænsninger

- `DRAFT` findes i modellen, men bruges ikke som central driftsstatus i admin-overblikket
- `NOT_HOME_HISTORY` er ikke en rigtig enum-status
- `NOT_HOME_HISTORY` bruges som filter- og historikbegreb i UI

## Hvordan seneste status findes

Dashboard og adresseoversigter tager udgangspunkt i den seneste relevante aftale pr. adresse.

Logikken er i store træk:

1. hent aftaler for adressen i omvendt dato-rækkefølge
2. brug seneste status blandt de relevante statusser
3. hvis kun `NOT_SCHEDULED` findes, bruges den
4. hvis adressen har `register_closed = true`, behandles den som `CLOSED`

Det betyder, at adresseoverblik og historik ikke nødvendigvis viser alle gamle trin, men den aktuelle udledte status.

## Dashboard-tællinger

Admin-dashboardet udleder følgende hovedtællinger:

| Felt | Hvordan det beregnes |
|---|---|
| `Præ total` | `SCHEDULED + INFORMED` |
| `Post total` | `COMPLETED + CLOSED` |
| `Ikke hjemme` | Antal `NOT_HOME` hændelser i historikken |
| `Behov for ny dato` | Adresser med seneste status `NEEDS_RESCHEDULE` |
| `Total adresse` | Alle adresser |
| `Mangler i alt` | Adresser som ikke er i planlagt/informeret/skiftet/afsluttet/ikke hjemme/behov for ny dato |
| `Lager` | Sum af alle lagerbevægelser |
| `Beskeder` | Antal unikke adresser med beboerbesked |

Vigtigt:

- kortet `Ikke hjemme` viser historik-tælling, ikke kun nuværende aktive adresser
- `Mangler i alt` er en afledt restgruppe

## Arbejdsdage status

Dashboardet grupperer arbejdsdage ud fra `vvs_availability.date`.

For hver dag beregnes blandt andet:

- total antal aftaler
- planlagte
- informerede
- skiftede
- afsluttede
- ikke hjemme
- færdigprocent

Dagene bliver desuden opdelt i:

- i dag
- kommende
- seneste 7 dage
- ældre historik

## Fremdrift pr. vej

Vej-fremdrift beregnes pr. `street`:

- total adresser på vejen
- antal færdige adresser (`COMPLETED + CLOSED`)
- resterende adresser
- færdigprocent

Veje markeres som:

- `I gang`
- `Færdig`

## Typiske statusovergange

| Fra | Til | Eksempel |
|---|---|---|
| `NOT_SCHEDULED` | `SCHEDULED` | Planlægning commit |
| `SCHEDULED` | `INFORMED` | Brev/PDF genereres |
| `SCHEDULED` eller `INFORMED` | `NEEDS_RESCHEDULE` | Beboer anmoder om ny dato |
| `SCHEDULED` eller `INFORMED` | `COMPLETED` | Arbejde udføres og registreres |
| `COMPLETED` | `CLOSED` | Sag afsluttes |
| `SCHEDULED` eller `INFORMED` | `NOT_HOME` | Beboer var ikke hjemme |

## Relaterede sider

- [Admin-flow](admin-flow.md)
- [Fejlsøgning](troubleshooting.md)
