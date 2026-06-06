"""行级留痕标注（DESIGN ingest §7）。每行打来源/年份/抓取时间/原件哈希/解析器版本。

满足 SCHEMAS 强制字段 source_url/year/fetched_at + 内部审计字段 raw_hash/parser_version。
"""

PARSER_VERSION = "ingest-1.0"


def tag_rows(rows, source_url, year, fetched_at, raw_hash,
             parser_version=PARSER_VERSION, extra=None,
             source_org="", source_page="", source_file=""):
    """给每行附加留痕字段（不改原行其余内容）。返回新列表。

    为支持"用户细究来源"，除文件直链外另存：
      source_org  发布机构（如 广东省教育考试院）
      source_page 公告页URL（承载文件的官方公告，比直链更稳、有上下文）
      source_file 源文件名（当 source_url 是压缩包时，包内对应文件名；直链可留空）
    """
    out = []
    for r in rows:
        rec = dict(r)
        rec["source_url"] = source_url
        rec["year"] = year
        rec["fetched_at"] = fetched_at
        rec["raw_hash"] = raw_hash
        rec["parser_version"] = parser_version
        rec["发布机构"] = source_org
        rec["公告页URL"] = source_page
        rec["源文件名"] = source_file
        if extra:
            rec.update(extra)
        out.append(rec)
    return out
