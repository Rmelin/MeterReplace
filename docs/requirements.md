# Projektkrav & Funktioner (Planlægning / Lager / Breve / Opgaver)

## Overblik
Dokumentet beskriver krav og funktioner for admin- og VVS-flow, inkl. auto-planlægning, adresse-status, lagerjustering og breve.

---

## Auto-planlægning (Admin)
### Preview / Udkast
- Preview viser udkast, intet bliver planlagt før Commit.
- Overskrift i preview: “Resultat (udkast)” og “Planlagte adresser (udkast)”.
- Udkast kan omrokeres.

### Planlægningsrækkefølge (kilden til slot-tider)
- Planlægningsrækkefølge styrer den endelige rækkefølge og tidslommer.
- Drag-and-drop i Planlægningsrækkefølge.
- Planlagte adresser (udkast) opdateres efter rækkefølgen.
- Commit bruger rækkefølgen til at oprette `SCHEDULED`.

### Hoppet over / Ikke tilgængelig
- Ny liste: “Ikke tilgængelig”
  - Viser adresser der er unavailable i perioden (med dato/tid og note).
  - Viser også Fejl ved stophane.
- “Hoppet over” viser stadig målerbrønd‑adresser, men uden planlægningsregel.

---

## Unavailable-perioder (Adresser)
- Felt hedder “unavailable”.
- En adresse kan have flere perioder.
- Periode er dato + tid (fx 22/01/2026 15:30).
- Overlap-logik er inkluderende: start ≤ plan ≤ slut.
- UI i adresse-redigering:
  - Tilføj periode (start, slut, note).
  - Liste over perioder med slet.

---

## Status & Filtre
### Admin dashboard (`/admin/status`)
- Skal vise:
  - Planlagt
  - Beboer/kunde informeret
  - Skiftet
  - Afsluttet
  - Ikke hjemme (historik)
  - Behov for ny dato
  - Ikke planlagt
  - Total
  - Lager
- Alle bokse er links:
  - Planlagt → `status=planned`
  - Beboer/kunde informeret → `status=informed`
  - Skiftet → `status=completed`
  - Afsluttet → `status=closed`
  - Ikke hjemme → `status=not_home_history`
  - Behov for ny dato → `status=needs_reschedule`
  - Ikke planlagt → `status=unplanned`
  - Total → `/admin/addresses`
  - Lager → `/admin/inventory`

### Adresseoversigt (`/admin/addresses`)
- Status-kolonne:
  - Skiftet DD/MM for COMPLETED
  - Afsluttet DD/MM for CLOSED
  - Informeret, planlagt til den DD/MM for INFORMED
  - Planlagt DD/MM
  - Ikke hjemme, Behov for ny dato
- Noter-kolonne:
  - Badges for Brev, Målerbrønd, Stophane, Ikke hjemme historik og 📷 når fotos findes
- Filter-chips over tabellen:
  - Alle, Planlagt, Beboer/kunde informeret, Skiftet, Afsluttet, Ikke hjemme (nuværende), Ikke hjemme (historik), Behov for ny dato, Ikke planlagt
- Detaljeside viser fotos for adressen med labels.

---

## Import afsluttet
- Import bruger `vvs_name` til at finde VVS-bruger.
- Hvis arbejdsdag allerede findes for datoen, springes rækken over.
- Hvis arbejdsdag mangler, oprettes den automatisk (08:00–16:00).
- Arbejdsdage er som standard 08:00-16:00, men kan registreres mellem 06:00 og 20:00.
- Planlægningen bruger hele 30-minutters slots inden for den registrerede arbejdsdag.

---

## Mangler fotos
- Opsætning → "Mangler fotos" viser adresser med status Skiftet/Afsluttet uden billeder.
- Upload-formular matcher /admin/appointments (fototype + fil).

---

## Lager & Indkøb
- “Juster lager” knap åbner lille formular.
- Justering er kun fratræk.
- Note er påkrævet.
- Lager må gå i minus.
- Bevægelser viser label “Justering”.

---

## Breve
- Base URL styres via `PUBLIC_BASE_URL` (fallback til request).
- Beboerlink kan slås fra i brev-skabelonen (globalt).
- Når slået fra, vises link/QR ikke i preview eller PDF.
- Når PDF genereres, sættes status til "Beboer/kunde informeret".

---

## Opgaver
### Admin `/admin/appointments`
- Inline redigering uden ny side.
- Fejl vises inline.
- Foto-upload sætter status til "Skiftet".

### VVS `/vvs/tasks`
- Samme inline edit-mønster som admin.
- Foto-upload sætter status til "Skiftet".

---

## Design / Farver
- Admin: grøn `#22c55e`
- VVS: blå `#4da3ff`
- Default: orange `#f97316`

---

## Noter
- Ingen drafts gemmes i DB: udkast kun i preview.
- Planlægning sker først ved Commit.

---

## Proces-input
Udfyld dette ved ændringer i flowet:
- Formål:
- Hvem bruger funktionen:
- Berørte sider/flows:
- Datamodel-ændringer:
- Valideringer:
- UI-ændringer:
- Test/validering:
- Deploy/noter:
