# PDFTidy · 够用的 PDF 命令行工具

[![Python](https://img.shields.io/badge/python-3.8%2B-3776AB)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-12B76A)](LICENSE)

合并、拆分、抽页、旋转、加密、看信息——六件事一条命令搞定，不用打开任何图形软件。

```bash
pdftidy merge 合同1.pdf 合同2.pdf -o 全部合同.pdf
pdftidy extract 手册.pdf --pages 3-7,12 -o 精华版.pdf
```

## 为什么又造一个

这类小工具网上一堆，但要么是收费软件的「免费版」（加限制、打水印），要么只支持 Windows，要么装完之后发现合并 300 页的文件会崩。PDFTidy 的原则很简单：

- **只做六件事，每件都做对**：不追求 Read / Edit / OCR 全家桶
- **不修改源文件**：所有操作都是「读进来 → 写新文件」
- **报错要说人话**：密码错了就说密码错了，不会甩一堆 stack trace
- **纯 Python，跨平台**：Windows / macOS / Linux 行为一致

## 安装

```bash
pip install git+https://github.com/Liuyichen27/pdftidy.git
```

想让加密用上 AES-256（更安全）：

```bash
pip install "pdftidy[crypto] @ git+https://github.com/Liuyichen27/pdftidy.git"
```

## 六个命令

### merge · 合并

```bash
pdftidy merge a.pdf b.pdf c.pdf -o 合并结果.pdf
```

按命令行给出的**顺序**拼接，页序就是参数顺序。输出文件已存在会直接覆盖，但不允许覆盖任意一个输入文件。

### split · 拆分

```bash
pdftidy split 大文件.pdf              # 每页一个文件
pdftidy split 大文件.pdf -e 10        # 每 10 页一个文件
pdftidy split 大文件.pdf -e 2 -o ./out
```

输出名带页码范围，方便对回去：`大文件_p1-2.pdf`、`大文件_p3-4.pdf`……

### extract · 抽页

```bash
pdftidy extract 书.pdf --pages 3-7,12,20- -o 摘录.pdf
```

页码写法：

| 写法 | 含义 |
| --- | --- |
| `5` | 第 5 页 |
| `1-3` | 第 1 到 3 页 |
| `9-` | 第 9 页到结尾 |
| `-4` | 开头到第 4 页 |
| `3,7,10-12` | 混合，按顺序收 |

写反了（`7-3`）会自动理解成 `3-7`；超出总页数会直接告诉你这份文档有几页。

### rotate · 旋转

```bash
pdftidy rotate 扫描件.pdf -a 90            # 全部页面转 90°
pdftidy rotate 扫描件.pdf -a 180 --pages 2,5
```

只接受 90 的整数倍。注意这是改页面的旋转属性，不重新渲染，所以文件不会变大。

### encrypt / decrypt · 加密解密

```bash
pdftidy encrypt 私密.pdf -w 我的密码 -o 加密版.pdf
pdftidy decrypt 加密版.pdf -p 我的密码 -o 明文版.pdf
```

默认用 AES-256；没装 `cryptography` 会**自动退回 RC4-128** 并在输出里明确告诉你用的是哪个——不会偷偷降级。

密码忘了打不开，这个工具没有后门。

### slim · 瘦身

```bash
pdftidy slim 报告.pdf            # 生成 报告_slim.pdf
```

**说实话**：这个命令只压缩内容流、去掉重复对象，通常能省 5%~30%。它**不重采样图片**，所以扫描件类 PDF 别指望腰斩——那种要真正的 PDF 优化器（Ghostscript 之类）。压不动的时候它会直说「这份文件本来就紧凑」，不骗你。

### info · 看信息

```bash
pdftidy info 文档.pdf
```

```
文件      文档.pdf
大小      1.8 MB
页数      42
加密      否
版本      %PDF-1.7
页面尺寸  595 × 842 pt（A4）
元数据
  Title       季度报告
  Producer    Microsoft Word
```

页面尺寸混排会额外提示，一眼看出是不是有横向页混进来了。

## 处理加密文件

除了 `encrypt` 用 `-w` 指定**新密码**，其余命令都用 `-p` 提供**原密码**：

```bash
pdftidy merge 加密1.pdf 加密2.pdf -p 原密码 -o out.pdf
pdftidy extract 加密.pdf -p 原密码 --pages 1-2
```

不给密码打开加密文件会提示「请用 --password 提供密码」，而不是抛异常。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 处理失败（文件损坏等） |
| 2 | 参数或文件问题（路径不存在、页码越界、密码错） |

配合 `&&` 或脚本判断很方便。

## 作为库调用

```python
from pdftidy import core

core.merge(["a.pdf", "b.pdf"], "out.pdf")
core.extract("big.pdf", "part.pdf", pages="1-3")
print(core.info("doc.pdf").pages)
```

## 测试

```bash
python -m unittest discover -s tests -v
```

17 个用例，PDF 全部现场生成，不依赖任何外部样本。

## 已知限制

- 不支持扫描版的 OCR
- 不支持把 PDF 转 Word / Excel（那是另一类工具）
- `slim` 不重采样图片，压缩率有限
- 加密只保证「打开需要密码」，不防截图

## 许可

MIT License，详见 [LICENSE](LICENSE)。

---

<sub>English: PDFTidy is a small, focused PDF CLI for merging, splitting, extracting pages, rotating, encrypting/decrypting and inspecting metadata. It never modifies your input files, prints human-readable errors, and works the same on Windows, macOS and Linux. Encryption defaults to AES-256 and falls back to RC4-128 only when `cryptography` is unavailable — and tells you which one it used.</sub>
