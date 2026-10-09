import csv
from pathlib import Path

csv_path = Path(__file__).parent / "practice.csv"

with open(csv_path, newline="", encoding="utf-8") as file:
    reader = csv.DictReader(file)

    source_ids = []
    count = 0
    case_names = {}
    for row in reader:
        case_id = row["case_id"]
        case_name = row["case_name"]
        case_source = row["is_source"]
        case_names[case_id] = case_name

        if (case_source == "True"):
            count+=1
            source_ids.append(case_id)

    # print(source_ids)
    # print(case_names)

for case_id in source_ids:
    print(case_names[case_id])
