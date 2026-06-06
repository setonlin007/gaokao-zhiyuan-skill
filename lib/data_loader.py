"""从某省目录读取硬数据。纯 IO + 类型转换，无业务逻辑、无 LLM。

字段契约见 ../data/SCHEMAS.md。脏数据（缺强制字段 source_url/year）会被丢弃。
"""
import csv
import json
import os

REQUIRED_FIELDS = ("source_url", "year")  # fetched_at 缺失只告警不丢弃


def _to_int(value):
    """空串→None；可转则转 int。"""
    if value is None or str(value).strip() == "":
        return None
    return int(str(value).strip())


def load_timeline(province_dir):
    """读 时间线.json（P0 阶段判定 + 梯度配额用）。"""
    path = os.path.join(province_dir, "时间线.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_csv(path, int_fields=(), required=REQUIRED_FIELDS):
    """通用 CSV 读取：转 int、丢脏行。返回 list[dict]。"""
    rows = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # 丢弃缺强制字段的脏行
            if any(not str(row.get(k, "")).strip() for k in required):
                continue
            for k in int_fields:
                if k in row:
                    row[k] = _to_int(row[k])
            rows.append(row)
    return rows


def load_yifenyiduan(province_dir, kelei, year=None):
    """读 一分一段表.csv，按科类(+年份)过滤。返回 list[dict]。"""
    path = os.path.join(province_dir, "一分一段表.csv")
    rows = _load_csv(path, int_fields=("分数", "本段人数", "累计人数", "year"))
    out = [r for r in rows if r.get("科类") == kelei]
    if year is not None:
        out = [r for r in out if r.get("year") == year]
    return out


def load_subject_requirements(province_dir, kelei=None):
    """读 选科要求.csv（Q1 第一硬过滤器）。"""
    path = os.path.join(province_dir, "选科要求.csv")
    rows = _load_csv(path, int_fields=("year",))
    if kelei is not None:
        rows = [r for r in rows if r.get("科类") in (kelei, "不限")]
    return rows


def load_min_ranks(province_dir, kelei=None):
    """读 投档单位最低位次.csv（近3年，每年一行）。"""
    path = os.path.join(province_dir, "投档单位最低位次.csv")
    rows = _load_csv(path, int_fields=("year", "最低分", "最低位次"))
    if kelei is not None:
        rows = [r for r in rows if r.get("科类") == kelei]
    return rows


def load_plans(province_dir, kelei=None):
    """读 招生计划.csv（大小年修正用）。可选文件，缺失返回 []。"""
    path = os.path.join(province_dir, "招生计划.csv")
    if not os.path.exists(path):
        return []
    rows = _load_csv(path, int_fields=("year", "计划数"))
    if kelei is not None:
        rows = [r for r in rows if r.get("科类") == kelei]
    return rows
