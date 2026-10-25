"""PDF 操作的核心实现，和命令行参数解析分开，方便单独测试。

所有函数都是「读进去 → 写出新文件」，不修改源文件。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def parse_pages(spec: str, total: int) -> list[int]:
    """把 "1-3,7,9-" 解析成 0 基页码列表。

    页码按人类习惯从 1 开始，返回的索引从 0 开始。
    允许 "5-" 表示从第 5 页到结尾。
    """
    if not spec or not spec.strip():
        return list(range(total))

    out: list[int] = []
    for chunk in spec.replace("，", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            left, _, right = chunk.partition("-")
            left = left.strip()
            right = right.strip()
            start = int(left) if left else 1
            end = int(right) if right else total
            if start > end:
                start, end = end, start
            out.extend(range(start, end + 1))
        else:
            out.append(int(chunk))

    seen: set[int] = set()
    pages: list[int] = []
    for p in out:
        if p < 1 or p > total:
            raise ValueError(f"页码 {p} 超出范围（这份文档共 {total} 页）")
        if p - 1 not in seen:
            seen.add(p - 1)
            pages.append(p - 1)
    return pages


def open_reader(path: str | os.PathLike, password: str | None = None) -> PdfReader:
    """打开 PDF，需要密码就解一下。"""
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        if password is None:
            raise ValueError(f"{path} 是加密文件，请用 --password 提供密码")
        result = reader.decrypt(password)
        if not result:
            raise ValueError(f"密码不对，打不开 {path}")
    return reader


def merge(inputs: list[str], output: str, password: str | None = None) -> int:
    """按顺序合并多个 PDF，返回总页数。"""
    if len(inputs) < 2:
        raise ValueError("合并至少要两个文件")

    writer = PdfWriter()
    for path in inputs:
        reader = open_reader(path, password)
        writer.append(reader)

    out = Path(output)
    if out.exists() and out.resolve() in {Path(p).resolve() for p in inputs}:
        raise ValueError("输出文件不能覆盖输入文件")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return len(writer.pages)


def extract(src: str, output: str, pages: str | None = None,
            password: str | None = None) -> int:
    """抽取指定页码，另存为新文件。"""
    reader = open_reader(src, password)
    idx = parse_pages(pages, len(reader.pages)) if pages else list(range(len(reader.pages)))
    if not idx:
        raise ValueError("没有选中任何页")

    writer = PdfWriter()
    for i in idx:
        writer.add_page(reader.pages[i])

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return len(writer.pages)


def split(src: str, out_dir: str, every: int = 1,
          password: str | None = None) -> list[Path]:
    """按每 N 页切成若干文件，返回生成的文件列表。"""
    if every < 1:
        raise ValueError("--every 必须 >= 1")

    reader = open_reader(src, password)
    total = len(reader.pages)
    stem = Path(src).stem
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    produced: list[Path] = []
    for start in range(0, total, every):
        end = min(start + every, total)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])
        dst = out_root / f"{stem}_p{start + 1}-{end}.pdf"
        with open(dst, "wb") as f:
            writer.write(f)
        produced.append(dst)
    return produced


def rotate(src: str, output: str, angle: int = 90, pages: str | None = None,
           password: str | None = None) -> int:
    """把页面旋转 angle 度（90 的倍数），返回处理页数。"""
    if angle % 90 != 0:
        raise ValueError("旋转角度必须是 90 的整数倍")

    reader = open_reader(src, password)
    total = len(reader.pages)
    idx = set(parse_pages(pages, total)) if pages else set(range(total))

    writer = PdfWriter()
    for i in range(total):
        page = reader.pages[i]
        if i in idx:
            page.rotate(angle)
        writer.add_page(page)

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return len(idx)


def encrypt(src: str, output: str, password: str, owner: str | None = None,
            password_in: str | None = None) -> str:
    """给 PDF 加密，返回实际使用的算法名。

    AES-256 需要 cryptography 包；没装就退回 RC4-128，并在返回值里如实告知。
    """
    if not password:
        raise ValueError("密码不能为空")

    reader = open_reader(src, password_in)
    writer = PdfWriter()
    writer.append(reader)

    algorithm = "AES-256"
    try:
        writer.encrypt(user_password=password, owner_password=owner or password,
                       algorithm="AES-256")
    except Exception as e:
        # 没有 cryptography 时 pypdf 会抛 DependencyError，老版本则是 TypeError
        if "cryptography" not in str(e) and not isinstance(e, TypeError):
            raise
        writer = PdfWriter()
        writer.append(reader)
        try:
            writer.encrypt(user_password=password, owner_password=owner or password,
                           algorithm="RC4-128")
            algorithm = "RC4-128"
        except TypeError:  # 更老的版本连 algorithm 参数都没有
            writer.encrypt(user_password=password, owner_password=owner or password)
            algorithm = "RC4-128"

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return algorithm


def decrypt(src: str, output: str, password: str | None = None) -> None:
    """去掉密码保护，存成不加密的版本。"""
    reader = open_reader(src, password)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)


def slim(src: str, output: str, password: str | None = None) -> tuple[int, int]:
    """尽力压一压：压缩内容流、去掉重复对象。

    这不是重采样图片的「真压缩」，只是把 PDF 结构里能省的地方省掉，
    通常能掉 5%~30%，图片多的扫描件效果有限。返回 (原大小, 新大小)。
    """
    reader = open_reader(src, password)
    writer = PdfWriter(clone_from=reader)

    for page in writer.pages:
        try:
            page.compress_content_streams()
        except Exception:
            pass  # 个别损坏的流压不了，跳过，不影响整体
    try:
        writer.compress_identical_objects()
    except Exception:
        pass

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)
    return os.path.getsize(src), os.path.getsize(out)


@dataclass
class PdfInfo:
    path: str
    pages: int
    encrypted: bool
    size: int
    version: str = ""
    metadata: dict = field(default_factory=dict)
    page_sizes: list[tuple[float, float]] = field(default_factory=list)

    @property
    def size_h(self) -> str:
        n = float(self.size)
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} GB"


def info(src: str, password: str | None = None) -> PdfInfo:
    """读基本信息，不写任何文件。"""
    reader = PdfReader(str(src))
    encrypted = reader.is_encrypted
    if encrypted and password is not None:
        reader.decrypt(password)

    meta = {}
    try:
        raw = reader.metadata or {}
        for k, v in raw.items():
            meta[str(k).lstrip("/")] = str(v)
    except Exception:
        meta = {}

    sizes = []
    for page in reader.pages[:50]:  # 只取前 50 页，够看尺寸了
        box = page.mediabox
        sizes.append((round(float(box.width), 1), round(float(box.height), 1)))

    return PdfInfo(
        path=str(src),
        pages=len(reader.pages),
        encrypted=encrypted,
        size=os.path.getsize(src),
        version=str(getattr(reader, "pdf_header", "") or ""),
        metadata=meta,
        page_sizes=sizes,
    )
