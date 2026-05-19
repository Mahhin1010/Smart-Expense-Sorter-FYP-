import csv

with open(r'D:\my_django_project\CSV Upload Test\hybrid_pakistani_transactions_SyntheticDataset Expanded.csv', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

print(f"Total rows: {len(rows)}")
print(f"Columns: {list(rows[0].keys())}")

# Category distribution
from collections import Counter
cat_dist = Counter(r['Target_Category'] for r in rows)
print(f"\n--- Category Distribution ---")
for cat, count in cat_dist.most_common():
    print(f"  {cat}: {count}")

# Transaction type distribution
type_dist = Counter(r['Transaction_Type'] for r in rows)
print(f"\n--- Transaction Type Distribution ---")
for t, count in type_dist.most_common():
    print(f"  {t}: {count}")

# Comments analysis
comments_filled = [r for r in rows if r['Comments'].strip()]
print(f"\nRows WITH comments: {len(comments_filled)}/{len(rows)}")

# Print sample rows
print(f"\n--- Sample rows (first 15) ---")
print(f"{'Merchant':<22} | {'Type':<17} | {'Amount':>10} | {'Comments':<35} | {'Category'}")
print("-" * 120)
for r in rows[:15]:
    print(f"{r['Merchant_Name']:<22} | {r['Transaction_Type']:<17} | {r['Amount']:>10} | {r['Comments']:<35} | {r['Target_Category']}")
