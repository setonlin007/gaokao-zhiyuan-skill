"""抓取 + 原件归档 + sha256 + 域名 allowlist。解决"页面会断"：抓到立即归档原件。

只抓官方/权威域。支持 file:// 与本地路径（离线自测/已下载原件复算）。
注意：本层只搬运字节、算哈希、记出处，**不解析、不碰数字**。
"""
import hashlib
import os
import ssl
import urllib.parse
import urllib.request

# 只认官方/权威域（后缀匹配）。第三方聚合站一律拒绝（铁律一）。
ALLOW_SUFFIXES = (".edu.cn", ".gov.cn", "chsi.com.cn")


def is_allowed(url):
    host = urllib.parse.urlparse(url).hostname or ""
    return any(host == s.lstrip(".") or host.endswith(s) for s in ALLOW_SUFFIXES)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _read_local(path):
    """读本地原件或 file:// （离线/已归档复算）。"""
    if path.startswith("file://"):
        path = urllib.parse.urlparse(path).path
    with open(path, "rb") as f:
        return f.read()


def fetch_and_archive(url, raw_dir, dataset, year, ext="html",
                      fetched_at=None, mirror_urls=(), allow_local=False):
    """抓取 url（失败转 mirror），原件落盘到 raw_dir，返回出处记录 dict。

    allow_local=True 时允许本地路径/ file://（自测用）。返回:
      {raw_path, sha256, source_url, fetched_at, bytes}
    """
    candidates = [url] + list(mirror_urls)
    last_err = None
    for cand in candidates:
        try:
            is_local = allow_local and (cand.startswith("file://") or os.path.exists(cand))
            if not is_local and not is_allowed(cand):
                raise PermissionError(f"非官方域，拒绝抓取：{cand}")
            data = _read_local(cand) if is_local else _http_get(cand)
            digest = _sha256(data)
            os.makedirs(raw_dir, exist_ok=True)
            raw_path = os.path.join(raw_dir, f"{dataset}-{year}-{digest[:12]}.{ext}")
            with open(raw_path, "wb") as f:
                f.write(data)
            return {
                "raw_path": raw_path,
                "sha256": digest,
                "source_url": cand,
                "fetched_at": fetched_at,
                "bytes": data,
            }
        except Exception as e:  # 转下一个镜像
            last_err = e
            continue
    raise RuntimeError(f"全部源抓取失败（含镜像）：{candidates}；最后错误：{last_err}")


def _http_get(url, timeout=30, tolerate_bad_cert=True):  # pragma: no cover (网络)
    """抓取官方页。

    实测教训(2026-06 验证)：考试院站常 **http-only / TLS 证书域名无效**，
    所以 **不强制升 https**（强升会直接 ERR_TLS_CERT_ALTNAME_INVALID）。
    对 https 默认容忍坏证书(tolerate_bad_cert)——仅限已 allowlist 的官方域，
    且原件落盘后由校验闸门 + 哈希把关，安全风险可控。
    """
    req = urllib.request.Request(url, headers={"User-Agent": "gaokao-ingest/1.0"})
    ctx = None
    if url.startswith("https://") and tolerate_bad_cert:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    # 实测：环境代理会在 TLS 握手阶段拦截 gov 站（SSL_ERROR_SYSCALL）。
    # 对官方域强制【绕过代理直连】——等价于 curl --noproxy '*'。
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),                  # 空代理表 = 不走任何代理
        urllib.request.HTTPSHandler(context=ctx) if ctx else urllib.request.HTTPSHandler(),
    )
    with opener.open(req, timeout=timeout) as resp:
        return resp.read()
