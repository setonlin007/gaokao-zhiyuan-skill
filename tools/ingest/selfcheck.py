"""管线离线自测：抓取→解析→校验→落库，全程无网络、数字不经 LLM。

用合成"官方页面"夹具（_selfcheck_data/）：好数据应通过并写出带留痕 CSV；
非单调坏数据应被校验闸门拒收、不落库。运行：
    python3 /Users/setonlin/my-workspace/private/money/gaokao-zhiyuan-skill/tools/ingest/selfcheck.py
"""
import csv
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch
import ingest
import validate

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "_selfcheck_data")
OUT = os.path.join(FIX, "out")          # 自测落库目标（非真实 data/）
RAW = os.path.join(FIX, "raw")
FETCHED_AT = "2026-06-25"

PASS, FAIL = "✅", "❌"
_failures = []


def check(name, got, want):
    ok = got == want
    print(f"  {PASS if ok else FAIL} {name}: {got!r}" + ("" if ok else f"，期望 {want!r}"))
    if not ok:
        _failures.append(name)


def section(t):
    print("\n" + "=" * 60 + f"\n{t}\n" + "=" * 60)


def entry_for(fixture_name):
    """构造指向本地夹具的注册表条目（allow_local 路径）。"""
    return {
        "dataset": "一分一段表",
        "year": 2026,
        "format": "html_table",
        "primary_url": os.path.join(FIX, fixture_name),
        "table_selector": {"index": 1},   # 跳过 index 0 的装饰表
        "skip_rows": 1,
        "column_map": {"分数": 0, "本段人数": 1, "累计人数": 2},
        "const_cols": {"科类": "物理类"},
    }


# 清理上次产物
for d in (OUT, RAW):
    if os.path.exists(d):
        shutil.rmtree(d)

# ──────────────────────────────────────────────────────────────
section("测试1 · 域名 allowlist（只认官方/权威）")
check("考试院 .edu.cn 允许", fetch.is_allowed("https://www.hbea.edu.cn/x.html"), True)
check("教育厅 .gov.cn 允许", fetch.is_allowed("https://hbsjyt.gov.cn/x.html"), True)
check("阳光高考 chsi 允许", fetch.is_allowed("https://gaokao.chsi.com.cn/x"), True)
check("第三方聚合站 拒绝", fetch.is_allowed("https://www.gaokao-jigou.com/x"), False)

# ──────────────────────────────────────────────────────────────
section("测试2 · 好数据：抓取→解析→校验→落库")
r = ingest.run_dataset(entry_for("一分一段_good.html"), "湖北",
                       RAW, OUT, FETCHED_AT, total=21300, allow_local=True)
check("ingest 通过", r["ok"], True)
check("落库 5 行", r.get("rows"), 5)
check("原件已归档", os.path.exists(r["raw_path"]), True)
check("sha256 已记录", len(r.get("sha256", "")), 64)

out_csv = os.path.join(OUT, "湖北", "一分一段表.csv")
with open(out_csv, encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
check("CSV 行数", len(rows), 5)
check("选中正确的表(分数600→累计20000)",
      next(x["累计人数"] for x in rows if x["分数"] == "600"), "20000")
check("留痕 source_url 存在", bool(rows[0]["source_url"]), True)
check("留痕 year", rows[0]["year"], "2026")
check("留痕 fetched_at", rows[0]["fetched_at"], FETCHED_AT)
check("留痕 raw_hash 存在", len(rows[0]["raw_hash"]), 64)
check("const_col 科类 注入", rows[0]["科类"], "物理类")

# ──────────────────────────────────────────────────────────────
section("测试3 · 坏数据（累计非单调）→ 必须被拒、不落库")
r2 = ingest.run_dataset(entry_for("一分一段_bad.html"), "湖北",
                        RAW, OUT, FETCHED_AT, total=21300, allow_local=True)
check("ingest 被拒", r2["ok"], False)
check("拒因=校验未过", r2.get("reason"), "校验未过")
print(f"     校验报错：{r2.get('errors')}")
# 坏数据不应污染已落库的好快照（仍是 5 行好数据）
with open(out_csv, encoding="utf-8") as f:
    rows_after = list(csv.DictReader(f))
check("坏数据未污染已落库快照", len(rows_after), 5)
check("坏数据原件仍归档(可审计)", os.path.exists(r2.get("raw_path", "")), True)

# ──────────────────────────────────────────────────────────────
section("测试4 · 幂等：重跑好数据不应增行")
r3 = ingest.run_dataset(entry_for("一分一段_good.html"), "湖北",
                        RAW, OUT, FETCHED_AT, total=21300, allow_local=True)
check("重跑仍通过", r3["ok"], True)
check("文件内总行数仍为5(按主键去重)", r3["total_in_file"], 5)

# ──────────────────────────────────────────────────────────────
section("测试5 · 算术恒等校验抓 OCR 单字错（单调性抓不到的）")
# 模拟图片/OCR 源：本段人数被错读(600→500)，但累计仍单调——单调性测不出，恒等式能抓。
ocr_rows = [
    {"分数": "602", "本段人数": "500", "累计人数": "19000"},
    {"分数": "601", "本段人数": "500", "累计人数": "19500"},
    {"分数": "600", "本段人数": "500", "累计人数": "20000"},
    {"分数": "599", "本段人数": "500", "累计人数": "20600"},  # 本段应为600，OCR错读成500
]
ok_ocr, errs_ocr = validate.validate_yifenyiduan(ocr_rows)
check("OCR错读被算术恒等抓出", ok_ocr, False)
check("报错指向恒等不成立", any("算术恒等" in e for e in errs_ocr), True)
print(f"     {errs_ocr}")
# 对照：好数据(本段=600)恒等成立、应通过
good_rows = [dict(r) for r in ocr_rows]
good_rows[3]["本段人数"] = "600"
ok_good, _ = validate.validate_yifenyiduan(good_rows)
check("修正后恒等成立、通过", ok_good, True)

# ──────────────────────────────────────────────────────────────
section("自测结论")
if _failures:
    print(f"{FAIL} 失败 {len(_failures)} 项：{_failures}")
    sys.exit(1)
print(f"{PASS} 全部断言通过。自动获取管线工作正常：")
print("   官方域过滤 / 确定性解析 / 校验拒坏 / 留痕落库 / 幂等，全程无网络、数字不经 LLM。")
