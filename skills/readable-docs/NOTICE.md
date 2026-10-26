# 来源与许可

## ste-zh

以下内容改编自 ste-zh：

- 中文句式规则的分类。
- `scripts/check.py` 里的句式检查，包括：
  - 营销词表和套话表。
  - 名词化、被动语态、复合体貌和含糊词的识别。
  - 同义词组及其后缀例外。
  - 按字计句长的口径。

来源：

- [lemonhall/asd-ste100-skill-zh](https://github.com/lemonhall/asd-ste100-skill-zh)，2026-10-03 版本 1.0.0。

其许可如下：

```
MIT License

Copyright (c) 2026 lemonhall

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

ste-zh 的规则分类又参考了英文上游 [danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill)（MIT）。ASD-STE100 标准正文和受控词表不在本仓库中。

## 编号可读

编号可读规则来自用户提出的规格，此前写在本机 harness skill 里。`bare-id-run` 的判定逻辑和测试用例移植自 harness skill 的 `check-id-readability.py`。
