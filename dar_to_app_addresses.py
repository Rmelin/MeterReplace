
import csv
import re

INPUT_FILE = "gadevang_3400.csv"
OUTPUT_FILE = "addresses_app.csv"

ZIP_DEFAULT = "3400"
CITY_DEFAULT = "Hillerød"

# Kun adresser der eksplicit ligger i Gadevang (landsbyen)
REQUIRED_PLACE = ", Gadevang,"

def split_street_and_house_no(adressebetegnelse: str):
    """
    'Gadevangsvej 12, Gadevang, 3400 Hillerød'
    -> ('Gadevangsvej', '12')
    """
    if not adressebetegnelse:
        return "", ""

    main = adressebetegnelse.split(",")[0].strip()

    match = re.match(r"^(.*?)[ ]+(\d+[A-Za-z]?)$", main)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    return main, ""

with open(INPUT_FILE, newline="", encoding="utf-8") as infile, \
     open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as outfile:

    reader = csv.DictReader(infile)

    fieldnames = ["street", "house_no", "zip", "city"]
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()

    for row in reader:
        adresse = row.get("adressebetegnelse", "").strip()

        # ❗ Filtrér kun Gadevang (landsby)
        if REQUIRED_PLACE not in adresse:
            continue

        street, house_no = split_street_and_house_no(adresse)

        # Spring tomme/ugyldige adresser over
        if not street or not house_no:
            continue

        writer.writerow({
            "street": street,
            "house_no": house_no,
            "zip": ZIP_DEFAULT,
            "city": CITY_DEFAULT
        })

print("✅ addresses_app.csv oprettet med street, house_no, zip, city")
