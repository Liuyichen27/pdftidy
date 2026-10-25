"""pdftidy 测试：PDF 现场生成，不依赖任何外部样本文件。"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pypdf import PdfReader, PdfWriter  # noqa: E402

from pdftidy import core  # noqa: E402


def make_pdf(path: Path, pages: int = 3, text_tag: str = "") -> Path:
    """生成一份 n 页的空白 PDF，用尺寸区分不同文件的页面。"""
    writer = PdfWriter()
    for i in range(pages):
        # 每页宽不同，方便验证「抽取的是不是对的那一页」
        writer.add_blank_page(width=600 + i, height=800)
    writer.add_metadata({"/Title": text_tag or "test"})
    with open(path, "wb") as f:
        writer.write(f)
    return path


class TestParsePages(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(core.parse_pages("1-3", 10), [0, 1, 2])
        self.assertEqual(core.parse_pages("2,5", 10), [1, 4])
        self.assertEqual(core.parse_pages("3-", 5), [2, 3, 4])
        self.assertEqual(core.parse_pages("-2", 5), [0, 1])
        self.assertEqual(core.parse_pages("5-3", 5), [2, 3, 4])  # 反着写也认

    def test_dedupes_and_keeps_order(self):
        self.assertEqual(core.parse_pages("3,1,3,1-2", 5), [2, 0, 1])

    def test_empty_means_all(self):
        self.assertEqual(core.parse_pages("", 3), [0, 1, 2])

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            core.parse_pages("9", 3)


class TestMerge(unittest.TestCase):
    def test_page_count_adds_up(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            a = make_pdf(d / "a.pdf", 2, "A")
            b = make_pdf(d / "b.pdf", 3, "B")
            out = d / "merged.pdf"

            n = core.merge([str(a), str(b)], str(out))
            self.assertEqual(n, 5)
            self.assertEqual(len(PdfReader(str(out)).pages), 5)

    def test_refuses_single_file(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            a = make_pdf(d / "a.pdf", 1)
            with self.assertRaises(ValueError):
                core.merge([str(a)], str(d / "out.pdf"))

    def test_refuses_overwriting_input(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            a = make_pdf(d / "a.pdf", 1)
            b = make_pdf(d / "b.pdf", 1)
            with self.assertRaises(ValueError):
                core.merge([str(a), str(b)], str(a))


class TestExtract(unittest.TestCase):
    def test_picks_the_right_pages(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            src = make_pdf(d / "src.pdf", 4)  # 每页宽度 600,601,602,603
            out = d / "part.pdf"

            n = core.extract(str(src), str(out), "2,4")
            self.assertEqual(n, 2)
            widths = [float(p.mediabox.width) for p in PdfReader(str(out)).pages]
            self.assertEqual(widths, [601, 603])


class TestSplit(unittest.TestCase):
    def test_split_every_page(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            src = make_pdf(d / "doc.pdf", 3)
            files = core.split(str(src), str(d / "out"), every=1)
            self.assertEqual(len(files), 3)
            for f in files:
                self.assertEqual(len(PdfReader(str(f)).pages), 1)

    def test_split_in_chunks(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            src = make_pdf(d / "doc.pdf", 5)
            files = core.split(str(src), str(d / "out"), every=2)
            self.assertEqual(len(files), 3)  # 2 + 2 + 1
            self.assertEqual([Path(f).name for f in files],
                             ["doc_p1-2.pdf", "doc_p3-4.pdf", "doc_p5-5.pdf"])


class TestRotate(unittest.TestCase):
    def test_rotation_applied_to_selected_pages(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            src = make_pdf(d / "src.pdf", 3)
            out = d / "rot.pdf"

            n = core.rotate(str(src), str(out), 90, "2")
            self.assertEqual(n, 1)

            pages = PdfReader(str(out)).pages
            self.assertNotEqual(pages[1].get("/Rotate"), 0)
            self.assertIn(pages[0].get("/Rotate"), (None, 0))

    def test_rejects_non_multiple_of_90(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            src = make_pdf(d / "src.pdf", 1)
            with self.assertRaises(ValueError):
                core.rotate(str(src), str(d / "o.pdf"), 45)


class TestEncryptDecrypt(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            src = make_pdf(d / "src.pdf", 2)
            enc = d / "enc.pdf"
            dec = d / "dec.pdf"

            core.encrypt(str(src), str(enc), "s3cret")
            self.assertTrue(PdfReader(str(enc)).is_encrypted)

            # 不给密码读不出内容
            with self.assertRaises(ValueError):
                core.open_reader(str(enc))

            # 密码错也不行
            with self.assertRaises(ValueError):
                core.open_reader(str(enc), "wrong")

            core.decrypt(str(enc), str(dec), "s3cret")
            self.assertFalse(PdfReader(str(dec)).is_encrypted)
            self.assertEqual(len(PdfReader(str(dec)).pages), 2)


class TestInfoAndSlim(unittest.TestCase):
    def test_info(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            src = make_pdf(d / "src.pdf", 3, "报告")
            got = core.info(str(src))
            self.assertEqual(got.pages, 3)
            self.assertFalse(got.encrypted)
            self.assertGreater(got.size, 0)
            self.assertEqual(got.metadata.get("Title"), "报告")

    def test_slim_produces_readable_file(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            src = make_pdf(d / "src.pdf", 3)
            out = d / "slim.pdf"
            before, after = core.slim(str(src), str(out))
            self.assertGreater(before, 0)
            self.assertTrue(out.exists())
            self.assertEqual(len(PdfReader(str(out)).pages), 3)


class TestCli(unittest.TestCase):
    def test_info_command_runs(self):
        from pdftidy import cli

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            src = make_pdf(d / "x.pdf", 2)
            self.assertEqual(cli.main(["info", str(src)]), 0)

    def test_missing_file_returns_2(self):
        from pdftidy import cli

        self.assertEqual(cli.main(["info", "nope-does-not-exist.pdf"]), 2)


if __name__ == "__main__":
    unittest.main()
