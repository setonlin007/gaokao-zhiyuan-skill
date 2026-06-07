"""山东选考科目要求建库（官方公告 PDF → per-投档单位 选考要求，3+3 语义）。

源：山东省教育招生考试院《公布普通高校拟在山东招生专业(类)选考科目要求的公告》
    NewsID=6819 的"2024通用版(本科)"PDF —— 适用于 2025/2026 年高考考生。文本PDF，确定性解析。
    列：国标院校代码 | 院校名称 | 国标专业代码 | 专业(类) | 选考科目要求 | 院校所在省份。

难点（已诚实处理，铁律一/四）：
  选考公告用【国标代码 + 完整专业名】，投档表用【山东自有投档代号 + 简写专业名】，无共享代码。
  → 只能按 (院校名, 基础专业名) 对齐。实测命中 89.2%。
  → matched 且键唯一 → 落库真选考要求（真过滤）；未匹配/键冲突 → 不落库（answer_q1 退回"待核对"，不臆造）。
  山东 3+3 选考语义：'不提科目要求'=不限；'X[,Y...](N门均须选考)'=列出科目全须选；'X(1门必须选考)'=该科必选。
    实测无"任选其一"形态；若出现"其中/即可/或"则标 要求类型=任选(交集非空即可)。

运行：python3 tools/ingest/run_shandong_xuanke.py
落库：data/provinces/山东/选考要求.csv（投档单位粒度，仅含可信匹配行）。数字/科目不经 LLM。
"""
import csv
import hashlib
import os
import re
import sys

import pypdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import provenance

YEAR = 2025
FETCHED_AT = "2026-06-07"
ORG = "山东省教育招生考试院"
XK_PDF = "/tmp/sd_xk_1.pdf"   # 2024通用版(本科)，适用2025/2026
XK_URL = "https://www.sdzk.cn/Floadup/file/20250317/6387782010007663213616549.pdf"
XK_PAGE = "https://www.sdzk.cn/NewsInfo.aspx?NewsID=6819"
TD_XLS = "/tmp/sd_toudang_2025.xls"

SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(SKILL, "data", "provinces", "山东", "选科要求.csv")
RAW_DIR = os.path.join(SKILL, "data", "_raw", "山东")

PROV = ("北京|天津|河北|山西|内蒙古|辽宁|吉林|黑龙江|上海|江苏|浙江|安徽|福建|江西|山东|河南|"
        "湖北|湖南|广东|广西|海南|重庆|四川|贵州|云南|西藏|陕西|甘肃|青海|宁夏|新疆|香港|澳门|台湾")
REC = re.compile(r"(\d{5,6})\s+([一-龥A-Za-z（）()·]+?)\s+([0-9A-Za-z]{4,6})\s+(.+?)\s+"
                 r"(不提科目要求|[一-龥,，/]+?\([^)]*?报考\))\s+(" + PROV + r")\b")
KNOWN_SUBJ = {"物理", "化学", "生物", "政治", "历史", "地理"}
PASS, FAIL = "✅", "❌"
fails = []


def check(name, got, want):
    ok = got == want
    print(f"  {PASS if ok else FAIL} {name}: {got!r}" + ("" if ok else f"，期望 {want!r}"))
    if not ok:
        fails.append(name)


def norm_major(name):
    """基础专业名 = 首个括号前部分，去空白（join 键，两边口径一致）。"""
    return re.split(r"[（(]", name, 1)[0].strip()


def parse_req(raw):
    """选考要求原文 → (要求类型, 科目list)。无法确定→(None,None) 表示不可信，调用方应丢弃。"""
    raw = raw.strip()
    if raw == "不提科目要求":
        return "不限", []
    head = re.split(r"[（(]", raw, 1)[0]  # 括号前的科目串
    subj = [s.strip().replace("思想政治", "政治") for s in re.split(r"[,，/]", head) if s.strip()]
    if not subj or any(s not in KNOWN_SUBJ for s in subj):
        return None, None
    if "其中" in raw or "即可" in raw or "/" in head:
        return "任选", subj
    if "均须" in raw or "必须" in raw:
        return "均须", subj
    return None, None


def archive(path, label):
    with open(path, "rb") as f:
        b = f.read()
    h = hashlib.sha256(b).hexdigest()
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(os.path.join(RAW_DIR, f"{label}-{YEAR}-{h[:12]}.pdf"), "wb") as f:
        f.write(b)
    print(f"原件归档: {label}  sha256={h[:16]}…  bytes={len(b)}")
    return h


# ① 解析选考公告 → 索引 (院校名, 基础专业名) -> (要求类型, 科目)
print("解析选考公告本科PDF…")
xk_hash = archive(XK_PDF, "选考要求-本科")
reader = pypdf.PdfReader(XK_PDF)
full = re.sub(r"\s+", " ", " ".join((p.extract_text() or "") for p in reader.pages))
index, conflict, bad_req = {}, set(), 0
for m in REC.finditer(full):
    yxmc, zymc, raw = m.group(2).strip(), m.group(4).strip(), m.group(5).strip()
    typ, subj = parse_req(raw)
    if typ is None:
        bad_req += 1
        continue
    key = (yxmc, norm_major(zymc))
    val = (typ, tuple(subj), raw)
    if key in index and index[key] != val:
        conflict.add(key)        # 同(院校,基础专业)出现不同要求 → 模糊，标冲突后丢弃
    else:
        index[key] = val
for k in conflict:
    index.pop(k, None)
print(f"  选考记录入索引 {len(index)} 条；冲突丢弃 {len(conflict)} 键；无法解析要求 {bad_req} 条")
check("选考索引 > 40000", len(index) > 40000, True)

# ② join 到 2025 投档单位（按 院校名+基础专业名），matched 才落库
import xlrd
sh = xlrd.open_workbook(TD_XLS).sheet_by_index(0)
yx_re = re.compile(r"^([A-Z]\d{3,4})(.+)$")
zy_re = re.compile(r"^([0-9A-Za-z]+)(.+)$")
rows, total, matched, miss = [], 0, 0, 0
seen_uid = set()
for r in range(2, sh.nrows):
    zy = str(sh.cell_value(r, 0)).strip()
    yx = str(sh.cell_value(r, 1)).strip()
    if not zy or not yx:
        continue
    mz, my = zy_re.match(zy), yx_re.match(yx)
    if not mz or not my:
        continue
    total += 1
    yxmc, zymc = my.group(2).strip(), mz.group(2).strip()
    uid = f"{my.group(1)}-{mz.group(1)}"
    hit = index.get((yxmc, norm_major(zymc)))
    if not hit:
        miss += 1
        continue
    typ, subj, raw = hit
    if uid in seen_uid:
        continue
    seen_uid.add(uid)
    matched += 1
    rows.append({"投档单位id": uid, "院校名": yxmc, "专业组代码": mz.group(1),
                 "专业名": zymc, "科类": "综合",
                 "要求类型": typ, "要求科目": ",".join(subj), "选考要求原文": raw})
rate = matched / total * 100
print(f"  投档单位 {total}；选考真匹配 {matched} ({rate:.1f}%)；未匹配 {miss}（→answer_q1 退回'待核对'）")
check("匹配率 > 85%", rate > 85, True)
# 校验：要求科目都在已知6科；要求类型枚举
enum_ok = all(r["要求类型"] in ("不限", "均须", "任选") for r in rows)
subj_ok = all(all(s in KNOWN_SUBJ for s in r["要求科目"].split(",") if s) for r in rows)
check("要求类型枚举合法", enum_ok, True)
check("要求科目均为已知6科", subj_ok, True)
# 已知事实抽查：北大理科试验班类=物理+化学均须
bd = [r for r in rows if r["投档单位id"].startswith("A001-") and "理科试验班" in r["专业名"]]
if bd:
    print(f"     抽查 北大理科试验班: 要求={bd[0]['要求类型']} 科目={bd[0]['要求科目']}")
    check("北大理科试验班=均须物理,化学", (bd[0]["要求类型"], set(bd[0]["要求科目"].split(","))),
          ("均须", {"物理", "化学"}))

# ③ 留痕落库
if not fails:
    tagged = provenance.tag_rows(rows, XK_URL, YEAR, FETCHED_AT, xk_hash,
                                 source_org=ORG, source_page=XK_PAGE)
    fields = list(tagged[0].keys())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(tagged)
    print(f"\n落库: 选科要求.csv = {len(tagged)} 行 → {OUT}")

print()
if fails:
    print(f"{FAIL} 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print(f"{PASS} 山东选考要求建库成功（真匹配部分）：确定性解析+保守对齐，未匹配诚实留'待核对'。")
