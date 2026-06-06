"""编排：registry → fetch → parse → provenance → validate → publish。

流程任一步失败即拒绝该快照（不落库、保留上一个 good）。数字全程确定性。
"""
import csv
import json
import os

import fetch
import parse
import provenance
import validate

# 每个数据集的落库文件名 + 合并主键（多年共存按主键去重）
DATASET_FILES = {
    "一分一段表": ("一分一段表.csv", ["科类", "分数", "year"]),
    "投档单位最低位次": ("投档单位最低位次.csv", ["投档单位id", "year"]),
    "招生计划": ("招生计划.csv", ["投档单位id", "year"]),
    "选科要求": ("选科要求.csv", ["投档单位id", "year"]),
}


def load_registry(sources_dir, province):
    path = os.path.join(sources_dir, f"{province}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _publish_csv(path, new_rows, key_cols):
    """合并写入：读旧行，剔除同主键的，并入新行，按字段并集写回。"""
    existing = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    new_keys = {tuple(str(r.get(k, "")) for k in key_cols) for r in new_rows}
    merged = [r for r in existing
              if tuple(str(r.get(k, "")) for k in key_cols) not in new_keys]
    merged.extend(new_rows)
    # 字段顺序：以新行字段为准 + 旧行多出的字段
    fields = list(new_rows[0].keys())
    for r in merged:
        for k in r:
            if k not in fields:
                fields.append(k)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in merged:
            w.writerow(r)
    return len(merged)


def run_dataset(entry, province, raw_dir, data_dir, fetched_at,
                total=None, allow_local=False, static_cols=None):
    """跑单个数据集 ingest。返回结果 dict（含 ok / reason / 落库条数）。"""
    dataset = entry["dataset"]
    year = entry["year"]

    # ① + ② 抓取归档
    got = fetch.fetch_and_archive(
        entry["primary_url"], raw_dir, dataset, year,
        ext=entry.get("ext", "html"), fetched_at=fetched_at,
        mirror_urls=entry.get("mirror_urls", ()), allow_local=allow_local,
    )

    # ③ 确定性解析
    parser = parse.DISPATCH[entry["format"]]
    if entry["format"] == "html_table":
        rows = parser(got["bytes"].decode("utf-8"),
                      entry["table_selector"], entry["column_map"],
                      skip_rows=entry.get("skip_rows", 1))
    else:
        rows = parser(got["raw_path"], entry["table_selector"],
                      entry["column_map"], skip_rows=entry.get("skip_rows", 1))

    # 注册表里声明的常量列（如 科类 / 投档单位id 拼接规则的静态部分）
    for r in rows:
        for k, v in (entry.get("const_cols") or {}).items():
            r.setdefault(k, v)
        if static_cols:
            r.update(static_cols)

    # ⑤ 校验闸门（在落库前）
    validator = validate.VALIDATORS[dataset]
    ok, errs = (validator(rows, total) if dataset in ("一分一段表", "投档单位最低位次")
                else validator(rows))
    if not ok:
        return {"ok": False, "dataset": dataset, "year": year,
                "reason": "校验未过", "errors": errs[:10], "raw_path": got["raw_path"]}

    # ④ 留痕标注
    tagged = provenance.tag_rows(rows, got["source_url"], year,
                                 fetched_at, got["sha256"])

    # ⑥ 落库版本化
    fname, key_cols = DATASET_FILES[dataset]
    out_path = os.path.join(data_dir, province, fname)
    n = _publish_csv(out_path, tagged, key_cols)
    return {"ok": True, "dataset": dataset, "year": year,
            "rows": len(tagged), "total_in_file": n,
            "out_path": out_path, "raw_path": got["raw_path"],
            "sha256": got["sha256"]}
