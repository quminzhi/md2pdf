# Markdown 转 PDF

首次克隆仓库后，用启动脚本指定的 Python 安装依赖：

```bash
/usr/local/bin/python3.14 -m pip install --target .md2pdf-lib -r requirements.txt
```

本地依赖和缓存不纳入 Git；中文字体及其许可证随仓库提供。
当前启动脚本使用 macOS 上的 `/usr/local/bin/python3.14`。
若使用其他 Python 解释器，请修改启动脚本，并用同一个解释器重新安装依赖。

在 Downloads 目录执行：

```bash
./tools/md2pdf cve-agent.md
./tools/md2pdf 任意文件.md -o 输出文件.pdf
```

fish 用户可将工具目录永久加入 PATH（当前机器已配置）：

```fish
fish_add_path --universal --append /Users/quminzhi/Downloads/tools
md2pdf "/路径/文档.md"
md2pdf "/路径/文档.md" -o "/路径/输出.pdf"
```

启动脚本使用本机的 `/usr/local/bin/python3.14`，以匹配自带的二进制依赖，
不受 fish 中 pyenv 默认 Python 版本的影响。

默认输出同名 PDF，保存在输入 Markdown 所在目录。默认样式为 A4、
黑白灰；正文采用思源黑体 Regular，主标题采用 Bold，小标题采用 Medium。
行内代码和代码块中的英文采用 Courier 等宽字体，中文及符号采用思源黑体。

命令、Python 脚本、依赖、中文字体均保存在本目录。

代码块正文为 8 pt、行距 11 pt；框内四边留白 9 pt，框线与前一段之间
至少保留 10 pt、与后一段之间至少保留 12 pt（约 3.5 / 4.2 mm）。
页首不额外插入外边距。短代码块尽量整块分页，长代码块允许跨页并标记“续”；
保留空行，Tab 按 4 列展开，过长的行在框内折行。代码前的说明段落与短示例
一起分页；长代码至少保留前 4 个显示行与说明同页，其余部分正常跨页。

支持段落、标题、引用、围栏代码块、简单列表和管道表格；保留 Markdown
强制换行、网页链接及显式 HTML 锚点跳转，标题自动生成 PDF 书签。
表格根据各列内容长度分配宽度，跨页重复表头；末两行能容纳在一页时保持
在一起，避免末行独占续页。以二级标题“目录”标识的目录采用紧凑字号和间距。

当前是轻量 Markdown 子集：暂不支持嵌套列表、多段列表项、图片、数学公式、
脚注或任意 HTML；中文与 Courier 混排的字符画不保证严格网格对齐。
PDF 中折行后的代码复制时可能需要手动合并换行，可执行代码仍以 Markdown 为准。

排版与内容回归检查：`python3 -B -m unittest -v test_md2pdf`。
