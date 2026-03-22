import csv

input_file = "DAR_V2_Adresse_TotalDownload_csv_Current_497.csv"
output_file = "gadevang_3400.csv"

with open(input_file, newline="", encoding="utf-8") as infile, \
     open(output_file, "w", newline="", encoding="utf-8") as outfile:

    reader = csv.DictReader(infile)
    writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
    writer.writeheader()

    for row in reader:
        adresse = row["adressebetegnelse"]
        if adresse and "Gadevang" in adresse and "3400" in adresse:
            writer.writerow(row)

print("Færdig – kun Gadevang, 3400 Hillerød")

