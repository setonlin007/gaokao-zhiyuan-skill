"""确定性解析层：把官方原件解析成行。数字只由这里按列索引产出，LLM 绝不参与。

已实现：html_table（stdlib，无依赖）。
预留接口：excel / pdf_text / pdf_scan —— 生产环境接 openpyxl / pdfplumber / OCR，
仍遵守"按列索引/坐标取值、不做语义猜测"原则。
"""
from html.parser import HTMLParser


class _TableExtractor(HTMLParser):
    """把 HTML 中所有 <table> 抽成 [ [ [cell,..](行) ,.. ](表) ,.. ]。纯结构，不解释内容。"""

    def __init__(self):
        super().__init__()
        self.tables = []
        self._cur_table = None
        self._cur_row = None
        self._cur_cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._cur_table = []
        elif tag == "tr" and self._cur_table is not None:
            self._cur_row = []
        elif tag in ("td", "th") and self._cur_row is not None:
            self._cur_cell = []

    def handle_data(self, data):
        if self._cur_cell is not None:
            self._cur_cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cur_cell is not None:
            self._cur_row.append("".join(self._cur_cell).strip())
            self._cur_cell = None
        elif tag == "tr" and self._cur_row is not None:
            self._cur_table.append(self._cur_row)
            self._cur_row = None
        elif tag == "table" and self._cur_table is not None:
            self.tables.append(self._cur_table)
            self._cur_table = None


def extract_tables(html_text):
    """返回页面里所有表格的二维结构。"""
    p = _TableExtractor()
    p.feed(html_text)
    return p.tables


def parse_html_table(html_text, table_selector, column_map, skip_rows=1):
    """按注册表配置确定性取值。

    table_selector: {"index": N} 选第 N 张表。
    column_map: {字段名: 列索引}。
    skip_rows: 跳过的表头行数（默认 1）。
    返回 list[dict]，值均为原始字符串（int 转换交给 ingest，便于校验脏值）。
    """
    tables = extract_tables(html_text)
    idx = table_selector.get("index", 0)
    if idx >= len(tables):
        raise ValueError(f"页面只有 {len(tables)} 张表，取不到第 {idx} 张")
    table = tables[idx][skip_rows:]
    rows = []
    for r in table:
        if not r:
            continue
        record = {}
        for field, col in column_map.items():
            if col >= len(r):
                raise ValueError(f"行列数不足：需要列 {col}，实际 {len(r)} 列：{r}")
            record[field] = r[col]
        rows.append(record)
    return rows


# ── 预留接口（生产环境实现，签名保持一致）─────────────────────────
def parse_excel(raw_path, table_selector, column_map, skip_rows=1):  # pragma: no cover
    raise NotImplementedError("excel 解析需 openpyxl；按列索引读，逻辑同 html_table")


def parse_pdf_text(raw_path, row_regex, fields):
    """文本PDF 确定性解析：pypdf 逐页抽文字 → 按行正则抽取为 dict。

    row_regex: 每个数据行的正则（捕获组顺序对应 fields）。非数据行(标题/表头/页眉)
               自然不匹配被跳过。
    fields: 字段名列表，与正则捕获组一一对应。
    数字由正则从 PDF 文本层取出，**不经 LLM**。
    """
    import re
    from pypdf import PdfReader

    pat = re.compile(row_regex)
    reader = PdfReader(raw_path)
    rows = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            line = line.strip()
            m = pat.match(line)
            if not m:
                continue
            groups = m.groups()
            if len(groups) != len(fields):
                raise ValueError(f"正则组数({len(groups)})与字段数({len(fields)})不符：{line}")
            rows.append({f: g.strip() for f, g in zip(fields, groups)})
    return rows


def parse_pdf_scan(raw_path, table_selector, column_map, skip_rows=1):  # pragma: no cover
    raise NotImplementedError("扫描件需双OCR交叉，低置信单元格送人工复核队列")


DISPATCH = {
    "html_table": parse_html_table,
    "excel": parse_excel,
    "pdf_text": parse_pdf_text,
    "pdf_scan": parse_pdf_scan,
}
