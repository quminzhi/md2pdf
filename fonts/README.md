# 中文字体

本模板使用思源黑体简体中文（Source Han Sans CN）的三个字重：

- Regular / 400：正文、表格、代码中的中文和符号
- Medium / 500：小标题、表头
- Bold / 700：主标题、章节标题、加粗文字

来源：Adobe 官方仓库
https://github.com/adobe-fonts/source-han-sans/tree/release/Variable/TTF/Subset

`SourceHanSansCN-VF.ttf` 是上游原始可变字体。为兼容 ReportLab，
三个固定字重由 FontTools 从原始字体实例化，保留完整字符集，
并按 SIL Open Font License 的保留名称要求将派生字体命名为
`Md2pdf Sans CN`。许可证见 `SourceHanSans-OFL.txt`。

字体随工具提供，无需安装到系统。转换时自动嵌入 PDF 所需字形。
英文代码采用 Courier 等宽字体。
