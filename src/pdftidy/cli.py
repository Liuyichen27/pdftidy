"""pdftidy 命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, core


def _human(n: int) -> str:
    v = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if v < 1024 or unit == "GB":
            return f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} GB"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdftidy",
        description="够用的 PDF 命令行工具箱：合并、拆分、提取、旋转、加密、瘦身。",
        epilog="例子：pdftidy merge a.pdf b.pdf -o 合并.pdf",
    )
    p.add_argument("-V", "--version", action="version", version=f"pdftidy {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    # merge
    m = sub.add_parser("merge", help="按顺序合并多个 PDF")
    m.add_argument("inputs", nargs="+", help="要合并的 PDF，按命令行顺序拼接")
    m.add_argument("-o", "--out", default="merged.pdf", help="输出文件（默认 merged.pdf）")
    m.add_argument("-p", "--password", help="输入文件密码")

    # split
    s = sub.add_parser("split", help="每 N 页切一个文件")
    s.add_argument("input")
    s.add_argument("-o", "--out-dir", default="split_out", help="输出目录")
    s.add_argument("-e", "--every", type=int, default=1, help="每几页一个文件（默认 1）")
    s.add_argument("-p", "--password")

    # extract
    e = sub.add_parser("extract", help="抽取指定页码另存")
    e.add_argument("input")
    e.add_argument("--pages", required=True, help='页码，如 "1-3,7,9-"')
    e.add_argument("-o", "--out", default="extracted.pdf")
    e.add_argument("-p", "--password")

    # rotate
    r = sub.add_parser("rotate", help="旋转页面")
    r.add_argument("input")
    r.add_argument("-a", "--angle", type=int, default=90, help="90 / 180 / 270")
    r.add_argument("--pages", help="只转这几页，默认全部")
    r.add_argument("-o", "--out", default="rotated.pdf")
    r.add_argument("-p", "--password")

    # encrypt / decrypt
    en = sub.add_parser("encrypt", help="加密")
    en.add_argument("input")
    en.add_argument("-w", "--password", required=True, help="要设置的打开密码")
    en.add_argument("--owner", help="所有者密码，默认同打开密码")
    en.add_argument("-o", "--out", default="encrypted.pdf")

    de = sub.add_parser("decrypt", help="去掉密码保护")
    de.add_argument("input")
    de.add_argument("-p", "--password", required=True)
    de.add_argument("-o", "--out", default="decrypted.pdf")

    # slim
    sl = sub.add_parser("slim", help="压缩结构、去冗余（不是重采样图片）")
    sl.add_argument("input")
    sl.add_argument("-o", "--out", help="默认在原名后加 _slim")
    sl.add_argument("-p", "--password")

    # info
    i = sub.add_parser("info", help="查看页数、大小、元数据")
    i.add_argument("input")
    i.add_argument("-p", "--password")

    return p


def cmd_info(path: str, password: str | None) -> int:
    d = core.info(path, password)
    print(f"文件      {d.path}")
    print(f"大小      {d.size_h}")
    print(f"页数      {d.pages}")
    print(f"加密      {'是' if d.encrypted else '否'}")
    if d.version:
        print(f"版本      {d.version}")
    if d.page_sizes:
        w, h = d.page_sizes[0]
        # A4 是 595x842pt，按这个换算个大概
        kind = "A4" if abs(w - 595) < 5 and abs(h - 842) < 5 else "自定义"
        print(f"页面尺寸  {w:g} × {h:g} pt（{kind}）")
        uniq = {s for s in d.page_sizes}
        if len(uniq) > 1:
            print(f"          共 {len(uniq)} 种尺寸，混合排版")
    if d.metadata:
        print("元数据")
        for k, v in d.metadata.items():
            if v and v.strip():
                print(f"  {k:<12} {v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.cmd == "info":
            return cmd_info(args.input, args.password)

        if args.cmd == "merge":
            n = core.merge(args.inputs, args.out, args.password)
            print(f"合并了 {len(args.inputs)} 个文件，共 {n} 页 → {args.out}")
            return 0

        if args.cmd == "split":
            files = core.split(args.input, args.out_dir, args.every, args.password)
            print(f"切成 {len(files)} 个文件，放在 {args.out_dir}/")
            for f in files[:10]:
                print(f"  {f.name}")
            if len(files) > 10:
                print(f"  …还有 {len(files) - 10} 个")
            return 0

        if args.cmd == "extract":
            n = core.extract(args.input, args.out, args.pages, args.password)
            print(f"抽出 {n} 页 → {args.out}")
            return 0

        if args.cmd == "rotate":
            n = core.rotate(args.input, args.out, args.angle, args.pages, args.password)
            print(f"旋转了 {n} 页 {args.angle}° → {args.out}")
            return 0

        if args.cmd == "encrypt":
            algo = core.encrypt(args.input, args.out, args.password, args.owner)
            print(f"已加密（{algo}）→ {args.out}")
            if algo != "AES-256":
                print("  提示：装 cryptography 可升级到 AES-256：pip install cryptography")
            print("  别忘了密码，忘了打不开，没有后门。")
            return 0

        if args.cmd == "decrypt":
            core.decrypt(args.input, args.out, args.password)
            print(f"已去除密码保护 → {args.out}")
            return 0

        if args.cmd == "slim":
            out = args.out or str(Path(args.input).with_name(Path(args.input).stem + "_slim.pdf"))
            before, after = core.slim(args.input, out, args.password)
            if after < before:
                pct = (before - after) / before * 100
                print(f"{_human(before)} → {_human(after)}，省 {pct:.1f}% → {out}")
            else:
                print(f"压不动（{_human(before)} → {_human(after)}），这份文件本来就紧凑")
            return 0

    except FileNotFoundError as e:
        print(f"找不到文件：{e.filename}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"处理失败：{type(e).__name__}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
