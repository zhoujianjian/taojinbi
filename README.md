# 淘金币自动领取（电脑端 ADB + OCR 视觉定位）

用电脑控制安卓手机，每天自动完成淘宝「淘金币」签到和日常任务。

不需要在手机上装任何 App（不需要 Hamibot / Auto.js），全程依赖：

- **ADB**：模拟点击、滑动、截屏
- **Windows 自带 OCR**：识别屏幕上的中文文字，按文字定位按钮（不怕淘宝改版换坐标）

## 原理

脚本每一步都是「截屏 → OCR 识别文字 → 找到目标按钮的坐标 → 模拟点击」：

```
电脑 (Python + ADB)          手机 (淘宝)
  ┌────────────┐   USB/无线   ┌──────────┐
  │ 截屏 screencap ├──────────►│ 当前页面   │
  │ OCR 识别文字  │             │           │
  │ 计算按钮坐标  │             │           │
  │ input tap    ├──────────►│ 模拟手指   │
  │ input swipe  │             │           │
  └────────────┘             └──────────┘
```

浏览器任务里淘宝要求「持续滑动才计时」，所以浏览类任务会用 `input swipe`
每 1.2 秒滑动一次，直到 OCR 检测到「已得」「任务完成」等提示为止。

## 环境要求

| 项目 | 要求 |
|------|------|
| 电脑 | Windows 10/11（OCR 用的是 Windows 自带能力）|
| Python | 3.8+ |
| 手机 | Android，开启 USB 调试，已安装并登录淘宝 |
| 连接 | USB 线连接（或无线 ADB，但重启后需重连）|

## 安装步骤

### 1. 安装 ADB

下载 [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools)，
解压后把目录加进 PATH，验证：

```cmd
adb version
```

### 2. 手机开启 USB 调试

设置 → 关于手机 → 连点「版本号」7 次开启开发者模式 →
开发者选项里打开「USB 调试」。

用 USB 线连接电脑，手机上弹出的授权框点「允许」：

```cmd
adb devices
```

能看到 `xxxxxx  device` 就说明连上了。

### 3. 安装 Python 依赖

本脚本只用到标准库，无需安装第三方包。

## 使用方法

```cmd
:: 完整流程：补领昨日 → 签到 → 做任务 → 领取奖励
python taojinbi_adb.py

:: 只识别不点击（调试用）
python taojinbi_adb.py --dry

:: 只签到，不做任务
python taojinbi_adb.py --no-task
```

跑一次大约 3~5 分钟（浏览类任务每项要滑 22 秒），**期间不要碰手机**。

日志写入 `logs/YYYY-MM-DD.log`，每一步的截图存在 `logs/shot_*.png`，
跑完看一眼日志和截图就知道成没成。

## 每天定时自动运行

用 Windows 任务计划，每天 9:00 自动执行。**推荐用 PowerShell 注册**（比 `schtasks` 稳，
某些安全策略会把 `schtasks.exe` 列入黑名单直接拦掉）：

以管理员身份打开 PowerShell，粘贴执行：

```powershell
$action  = New-ScheduledTaskAction -Execute "D:\taojinbi\run_taojinbi.bat"
$trigger = New-ScheduledTaskTrigger -Daily -At 09:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName "Taobao_Taojinbi_Daily" -Action $action -Trigger $trigger -Settings $settings -Force
```

（把 `D:\taojinbi\` 换成你实际存放本项目的目录）

查看 / 删除：

```powershell
Get-ScheduledTaskInfo -TaskName "Taobao_Taojinbi_Daily"     # 看下次运行时间、上次结果
Unregister-ScheduledTask -TaskName "Taobao_Taojinbi_Daily" -Confirm:$false   # 删掉
```

**注意**：

- 手机要保持插着 USB 且 ADB 授权有效
- 手机必须是解锁状态；设了锁屏密码的话脚本叫不醒它，
  需要把锁屏去掉或改为无密码
- 如果电脑当时关机/睡眠，`StartWhenAvailable` 会在开机后补跑一次
- 整个流程要跑 4~5 分钟（浏览类任务每项要滑 22 秒），期间不要碰手机

## 脚本行为细节

- **入口文案兼容**：淘宝的入口文案一直在变（`去赚金币` → `赚更多金币` → `快速赚`），
  脚本按 `TASK_ENTRY` 里的关键词依次匹配，不用改代码
- **自动滚回顶部**：淘宝会记住上次的滚动位置，进页面后脚本先滑回顶部再找按钮
- **弹窗处理**：只有「看不到页面主体」时才判定为全屏广告并用返回键关闭，
  避免把页面正文里的活动文案（如"加抵金"）误判成弹窗
- **昨日补领**：淘金币页出现「昨日未领」时会自动点掉
- **任务识别**：按「金币徽章 + 上方标题行」的面板结构识别任务，不依赖任务名
  （淘宝会轮换任务名称，按名字找会失效）
- **支付宝类任务跳过**：蚂蚁庄园、支付宝农场、蚂蚁森林一律不点，
  因为会跳到支付宝 App 导致回不来；答题类、搜索类也跳过
  （在 `taojinbi_adb.py` 的 `SKIP_WORDS` 里可调整）
- **完成检测**：浏览任务靠 OCR 识别「已得 ⓒxx」「任务完成」等提示确认完成，
  没检测到会补 10 秒再确认一次
- **领取奖励**：只在淘金币页/任务面板里点「领取」，
  跳过「免费领取」「试用领取」这类会跳转广告页的按钮
- **兜底**：找不到按钮会先按返回键重试，必要时重启淘宝重进

## 文件说明

| 文件 | 作用 |
|------|------|
| `taojinbi_adb.py` | 主脚本：导航 → 补领 → 签到 → 任务 → 领取 |
| `ocr.ps1` | Windows OCR 封装：输入截图路径，输出「文本 x y」 |
| `run_taojinbi.bat` | 定时任务入口（设置 UTF-8 编码后调用主脚本）|
| `taojinbi-auto.js` | 备用方案：Hamibot / Auto.js 用的无障碍脚本（如果以后想在手机本地跑）|

## 常见问题

**Q: 点错位置 / 跑一半卡住？**
看 `logs/shot_*.png` 里最新一张截图，确认页面停在哪，把卡住的截图和日志发出来对照调整。

**Q: OCR 识别不到文字？**
淘宝 H5 活动页动效很多，偶尔整页都识别不出来。脚本会按返回键退回上一页重试，
一般重试 1~2 次能恢复。如果反复失败，先手动把手机停在淘金币页再跑。

**Q: 任务面板里任务都显示已完成，脚本会怎样？**
输出「没有可做的任务了」然后正常结束，不会重复点击。

**Q: 换了手机 / 分辨率不一样？**
基本不用改——所有点击坐标都是 OCR 现场按文字位置算的，
只有「图标在文字标签上方多少像素」这类偏移量写死（`COIN_ICON_OFFSET = 60`），
换分辨率差别大的手机时可能需要微调这个值。

## 风险提示

模拟点击属于灰色地带，淘宝风控严格时理论上存在限流/账号风险。
签到和浏览类任务大量人在用，实际风险很低，但请自行斟酌。
