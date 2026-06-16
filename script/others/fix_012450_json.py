"""012450 JSON 중복 제거 및 regime_id 재할당"""
import json
import sys
sys.stdout.reconfigure(encoding="utf-8")

path = "data/012450/regime_news_summary_012450.json"
data = json.load(open(path, encoding="utf-8"))
print(f"원본: {len(data)}건")

# 날짜 기반 중복 제거
seen = {}
for r in data:
    key = r["start"] + "_" + r["end"]
    if key not in seen:
        seen[key] = r

unique = list(seen.values())
print(f"중복 제거 후: {len(unique)}건")

# 날짜 순 정렬 후 regime_id 재할당
unique.sort(key=lambda x: x["start"])
for i, r in enumerate(unique, 1):
    r["regime_id"] = i

with open(path, "w", encoding="utf-8") as f:
    json.dump(unique, f, ensure_ascii=False, indent=2)

print("저장 완료. 마지막 5건:")
for r in unique[-5:]:
    print(f"  regime_id={r['regime_id']:>3}  {r['start']}~{r['end']}  {r['direction']}")
