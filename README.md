# 看图精灵 (PicSprite)

[![release](https://img.shields.io/github/v/release/mew5748-alt/PicSprite?label=release)](https://github.com/mew5748-alt/PicSprite/releases/latest)
[![platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-2f6fed)](https://github.com/mew5748-alt/PicSprite/releases/latest)
[![license](https://img.shields.io/github/license/mew5748-alt/PicSprite)](LICENSE)

一个为 Windows 打造的轻量看图工具：打开快、能编辑、能批量、能压体积，日常看图基本不用再装第二个软件。

![主界面](tests/shots/01-viewer.png)

## 下载安装

到 [Releases](https://github.com/mew5748-alt/PicSprite/releases/latest) 下载 **`PicSprite-Setup-1.2.2.exe`**，双击按向导安装即可，无需 Python 环境。

- 单个 exe 安装包，约 100 MB，安装后占用约 252 MB
- 装到当前用户目录 `%LOCALAPPDATA%\Programs\PicSprite`，**不需要管理员权限**
- 自带卸载程序（开始菜单「卸载看图精灵」或 设置 → 应用）
- 可选把看图精灵加入图片的「打开方式」（不修改你的默认打开程序）
- 静默安装：`PicSprite-Setup-1.2.2.exe /S`（同样会注册“打开方式”，不想注册加 `/noassoc`）

```powershell
# 校验下载的安装包（值见 Release 里的 SHA256SUMS.txt）
Get-FileHash .\PicSprite-Setup-1.2.2.exe -Algorithm SHA256
```

## 功能一览

**看图**

- 支持 BMP / JPG / JPEG / PNG / GIF / ICO / TIFF / WebP / TGA / PSD 等常见格式
- 支持 iPhone 默认的 **HEIC / HEIF**（内置解码器，无需装扩展），也能另存为 HEIC
- 缩放（滚轮对准光标缩放）、拖动平移、适应窗口、1:1、全屏、幻灯片播放
- 自动按 EXIF 方向摆正手机照片；GIF 与多页 TIFF 可逐帧查看
- 缩略图墙：异步加载 + 磁盘缓存，切回文件夹秒开；支持筛选与多种排序
- 左侧目录树、右侧信息面板（尺寸/格式/体积/拍摄参数）、拖拽打开、最近文件夹记忆

**打印**

- 打印当前图片、选中的多张，或整个文件夹的全部图片
- 排版：每页 1 / 2 / 4 / 6 / 9 张（按纸张方向自动选横排还是竖排）、可调页边距与图片间距
- 缩放：适应区域（完整显示）/ 原始大小（不放大）/ 铺满区域（裁切）
- 可勾选在每张图下打印文件名与拍摄日期
- 对话框左侧是**所见即所得的分页预览**，翻页即可检查每一页，预览尺寸按打印机真实可打印区计算
- 不需要打印机也能用：一键**导出为 PDF**，导出后会问你是否用系统默认程序打开
- 对话框里直接**选择打印机**、切换**单面 / 双面**（长边翻转、短边翻转），纸张与质量走打印机驱动设置
- 直接调用系统打印机驱动，走的是 Windows 原生打印，不改动原图

**身份证打印**

- 选正反面两张照片，自动找出卡片边界并**裁成 85.6 × 54 mm 的实际尺寸**
- **自动摆正**：歪着拍会摆平，倒着拍或竖着拍也会自动转回正向——人像面看头像是否在右侧，国徽面看红色标识是否偏上
- 判错了随时手动转：每张卡下面有「↺ 逆时针」「↻ 顺时针」，一次 90°，转到满意为止，转完照样能继续调整裁剪
- 两张卡片按实际大小排在**一张 A4** 上，上下或左右排列、间距与页边距可调，可一次打多份
- 识别不准时点「调整裁剪」，在照片上拖个框就能手动指定，比例自动锁定为卡片比例
- 同样支持导出 PDF，拿去做电子存档或发给打印店

**编辑**

- 旋转 / 翻转：默认是**临时预览**（不动物文件），点保存才落盘；右键菜单里也可选"旋转并写入文件"直接永久生效
- 裁剪：自由比例或 1:1 / 4:3 / 16:9 / 原图比例，三分构图线 + 八向控制点 + 实时尺寸提示，Enter 确认
- 涂鸦：任意颜色、1–60px 粗细，直接画在图上
- 添加文字：字体 / 字号 / 加粗 / 倾斜 / 颜色 / 描边，放到图上后可拖动定位，Enter 确认
- 调整尺寸、撤销 / 重做（最多 15 步，按内存预算自动收敛）、放弃全部修改

**另存为 / 压缩**

- 一键转换格式：JPG / PNG / WebP / BMP / TIFF / GIF / ICO / HEIC，可带质量参数
- 保存时同时可改尺寸（百分比 / 长边 / 宽 / 高 / 精确宽高）并限制文件体积
- **压缩到指定大小**：先二分搜索 JPEG/WebP 质量，仍超标再逐级缩小尺寸，右侧实时预估体积
- 覆盖前自动备份到 `.picsprite_backup`，写盘采用临时文件 + 原子替换，不怕写坏原图

**批量**

- 批量重命名：变量 `{name} {n} {nn} {date} {time} {parent} {w} {h}`、起始序号、补零、查找替换、大小写
- 批量转换格式 / 批量调整尺寸 / 批量限制体积，可组合使用
- 输出到子文件夹、指定目录或原地覆盖，执行前有完整预览表与重名检测，进度可中止

**个性化**

- 全部快捷键可在「设置 → 快捷键」里重新绑定，带冲突检测、可一键恢复默认
- 「设置 → 右键菜单」可勾选、排序、增删右键菜单项
- 可调画布背景（深灰 / 中灰 / 浅色）、缩略图尺寸、幻灯片间隔、缓存上限

## 界面

| 看图 | 缩略图墙 |
| --- | --- |
| ![看图](tests/shots/01-viewer.png) | ![缩略图墙](tests/shots/04-grid.png) |

| 裁剪 | 涂鸦与加字 |
| --- | --- |
| ![裁剪](tests/shots/02-crop-mode.png) | ![编辑](tests/shots/03-edited.png) |

| 另存为（改格式/尺寸/体积） | 批量处理 |
| --- | --- |
| ![另存为](tests/shots/05-saveas.png) | ![批量](tests/shots/06-batch.png) |

| 打印（排版与分页预览） | 打印输出（每页 4 张，也可导出 PDF） |
| --- | --- |
| ![打印](tests/shots/print-02-4up.png) | ![打印输出](tests/shots/print-04-pdf.png) |

| 身份证打印 | 自动转正 + 手动旋转 |
| --- | --- |
| ![身份证打印](tests/shots/idcard-01-dialog.png) | ![旋转](tests/shots/idcard-05-rotated.png) |

| 身份证打印输出（一张 A4 正反面） |
| --- |
| ![身份证输出](tests/shots/idcard-02-pdf.png) |

| 设置（快捷键 / 右键菜单） | 右键菜单 |
| --- | --- |
| ![设置](tests/shots/07-settings.png) | ![右键菜单](tests/shots/08-menu.png) |

| 安装向导 |
| --- |
| ![安装向导](tests/shots/09-setup.png) |

## 运行

需要 Python 3.9+ 和三个依赖（HEIC 支持由 pillow-heif 提供）：

```bat
pip install -r requirements.txt
python main.py                 :: 打开上次的文件夹
python main.py D:\照片          :: 打开文件夹
python main.py D:\a.jpg        :: 打开单张图片
```

也可以直接双击 **`run.bat`**（用 pythonw 启动，不弹黑框）。

### 打包 exe

- 只要绿色版程序目录：双击 **`build_exe.bat`**，产物在 `dist\看图精灵\看图精灵.exe`，
  整个 `dist\看图精灵` 文件夹拷走即可在没装 Python 的电脑上运行。
- 要**安装包**：`python tools/build_release.py`，产物是 `dist\看图精灵-Setup-1.2.2.exe`
  （发布时重命名为 `PicSprite-Setup-<版本>.exe`，避免中文文件名在下载链接里出错）
  （自带解压安装引擎，安装/卸载/快捷方式/文件关联全部自实现，不依赖 Inno Setup）。

安装包支持 `/S` 静默安装、`/uninstall` 卸载。

## 快捷键

| 功能 | 快捷键 | 功能 | 快捷键 |
| --- | --- | --- | --- |
| 打开图片 | Ctrl+O | 上一张 / 下一张 | ← / → |
| 保存 / 另存为 | Ctrl+S / Ctrl+Shift+S | 放大 / 缩小 | Ctrl+= / Ctrl+- |
| 压缩到指定大小 | Ctrl+Alt+C | 适应窗口 / 100% | Ctrl+0 / Ctrl+1 |
| 向左 / 向右旋转 | Ctrl+L / Ctrl+Shift+R | 裁剪 / 涂鸦 / 文字 | C / D / T |
| 水平 / 垂直翻转 | Ctrl+H / Ctrl+J | 撤销 / 重做 | Ctrl+Z / Ctrl+Y |
| 缩略图墙 | Tab | 全屏 | F11 |
| 打印 | Ctrl+P | 打印预览 | Ctrl+Shift+P |
| 身份证打印 | Ctrl+Shift+I | 批量处理 | Ctrl+B |
| 幻灯片 | F6（Esc 退出） | 设为壁纸 | Ctrl+Alt+W |
| 重命名 / 删除 | F2 / Del | 设置 | Ctrl+, |
| 快捷键速查 | F1 | — | — |

## 目录结构

```
ImageViewer/
├─ main.py                 入口
├─ run.bat                 双击运行
├─ build_exe.bat           打包绿色版 exe
├─ installer/
│  └─ setup_main.py        安装/卸载程序（安装包 exe 的源码）
├─ tools/
│  ├─ build_release.py     一键产出安装包
│  ├─ push_asset.py        上传安装包到 GitHub Release
│  └─ make_icon.py         生成 assets/app.ico
├─ viewer/
│  ├─ config.py            动作注册表、快捷键默认值、配置读写
│  ├─ imageio.py           多格式读写、缩放、编码体积控制（核心）
│  ├─ canvas.py            画布：缩放/平移/旋转/裁剪/涂鸦/文字
│  ├─ grid.py              缩略图墙（异步加载 + 缓存）
│  ├─ thumbcache.py        缩略图磁盘缓存与 LRU 清理
│  ├─ batch.py             批量处理逻辑
│  ├─ printing.py          打印版面计算与绘制（打印 / 预览 / PDF 共用）
│  ├─ printdialog.py       打印窗口：排版选项 + 分页预览 + 导出 PDF
│  ├─ printerui.py         打印机选择 + 单/双面（打印与身份证共用）
│  ├─ idcard.py            身份证识别裁剪与 A4 实际尺寸排版
│  ├─ idcarddialog.py      身份证打印窗口（正反面、手动框选、导出）
│  ├─ dialogs.py           另存为/压缩/尺寸/文字/属性/快捷键速查
│  ├─ batchdialog.py       批量处理窗口
│  ├─ settingsdialog.py    设置窗口
│  ├─ mainwindow.py        主窗口与全部功能接线
│  ├─ icons.py             程序内绘制的线性图标
│  ├─ style.py             浅色主题样式表
│  └─ workers.py           后台线程任务
└─ tests/                  自测脚本与截图
```

## 数据位置

| 内容 | 路径 |
| --- | --- |
| 配置 | `%APPDATA%\PicSprite\settings.ini`（纯文本，可直接编辑/备份） |
| 缩略图缓存 | `%APPDATA%\PicSprite\thumbcache`（设置里可清空、可限容） |
| 覆盖前备份 | 图片所在目录下的 `.picsprite_backup` |

## 已知限制

- 动图（GIF）与多页 TIFF 在保存时会只保留当前帧，保存前会弹窗确认。
- 批量处理为了稳妥采用主线程外的逐个处理，超大图（>100MP）会慢一些。
- ICO 输出会自动补齐为正方形并按 16–256 多尺寸写入。
- 涂鸦与文字是"烧录"进像素的，撤销可回退，但保存后需重新编辑。
- 打印一批图片时，"整个文件夹"最多取前 50 张、"选中的图片"最多 100 张，避免一次解码过多图把内存吃满；长边会按张数自动降到 1600–4200px。
- 身份证自动裁剪靠边缘与亮度反差判断，遇到「白卡片放在白纸上、且没有阴影」这类极端情况可能识别不准，可用「调整裁剪」手动框选。
- 自动转正靠「头像在右侧 / 国徽偏上」两条线索，黑白扫描件、或者证件被大面积遮挡时可能判不出来，此时卡片保持原样，点「↺ 逆时针」「↻ 顺时针」手动转即可。

## 自测

```bat
python tests/test_core.py        :: 多格式读写 / 体积压缩 / 批量逻辑
python tests/test_flow.py        :: 真实文件的保存、备份、重命名、删除、快捷键
python tests/test_gui.py         :: 界面主流程 + 截图
python tests/test_dialogs.py     :: 批量转换/重命名/压缩/另存为 端到端
python tests/test_print.py       :: 版面计算 + 导出 PDF 后逐像素核对位置/页数/图注
python tests/test_print_gui.py   :: 打印对话框（分页、选项联动、打印机/双面）+ 截图
python tests/test_idcard.py      :: 身份证自动裁剪 + 四种朝向自动转正 + A4 物理尺寸（PDF 回读量像素）
python tests/test_idcard_gui.py  :: 身份证窗口（正反面、自动转正与手动旋转、手动框选、份数）+ 截图
python tests/test_heic.py        :: HEIC/HEIF 读取、缩略图、另存与压缩
python tests/test_setup_silent.py:: 安装包静默安装 → 启动 → 卸载（用 dist 里的 exe）
python tests/test_setup_gui.py   :: 安装向导图形流程（自动点「安装」，验证产物后清理）
```

安装包的两个测试都要先构建：`python tools/build_release.py`。
