# 淘宝淘金币 / 京东京豆 自动领取（电脑端 ADB + OCR 视觉定位）

用电脑控制安卓手机，每天自动完成**淘宝淘金币**和**京东京豆**的签到、浏览任务。

不需要在手机上装任何 App（不需要 Hamibot / Auto.js），全程依赖：

- **ADB**：模拟点击、滑动、截屏
- **Windows 自带 OCR**：识别屏幕上的中文文字，按文字定位按钮（不怕 App 改版换坐标）

| 脚本 | 平台 | 每日产出 |
|------|------|----------|
| `taojinbi_adb.py` | 淘宝淘金币 | 签到 120 金币 + 浏览任务（每项 30~60） |
| `jingdong.py` | 京东京豆 | 签到卡 + 浏览任务换刮卡（100 京豆 = 1 元） |

## 原理

脚本每一步都是「截屏 → OCR 识别文字 → 找到目标按钮的坐标 → 模拟点击」：

```
电脑 (Python + ADB)          手机 (淘宝/京东)
  ┌────────────┐   USB/无线   ┌──────────┐
  │ 截屏 screencap ├──────────►│ 当前页面   │
  │ OCR 识别文字  │             │           │
  │ 计算按钮坐标  │             │           │
  │ input tap    ├──────────►│ 模拟手指   │
  │ input swipe  │             │           │
  └────────────┘             └──────────┘
```

两个平台的浏览任务计时规则不一样，这是实现上最大的差别：

| | 淘宝 | 京东 |
|---|---|---|
| 计时方式 | **必须持续滑动**才计时（每 1.2 秒滑一次）| **停在页面**上就会倒计时，不用滑 |
| 任务时长 | 15~22 秒/项 | 6 秒/项 |
| 奖励 | 直接到账 | 换成「刮卡次数」，刮开才知道给多少 |

## 环境要求

| 项目 | 要求 |
|------|------|
| 电脑 | Windows 10/11（OCR 用的是 Windows 自带能力）|
| Python | 3.8+ |
| 手机 | Android，开启 USB 调试，已安装并登录淘宝 / 京东 |
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
:: 淘宝淘金币：补领昨日 → 签到 → 做任务 → 领取奖励
python taojinbi_adb.py

:: 京东京豆：签到卡 → 浏览任务 → 刮卡
python jingdong.py

:: 只识别不点击（调试用）
python taojinbi_adb.py --dry
python jingdong.py --dry

:: 只签到，不做任务
python taojinbi_adb.py --no-task
python jingdong.py --no-task
```

| 脚本 | 耗时 |
|------|------|
| 淘宝 | 3~5 分钟（每项任务要滑 22 秒）|
| 京东 | 2~4 分钟（每项停 8 秒，比淘宝快）|

**期间不要碰手机**。日志分别写入：

- 淘宝 `logs/YYYY-MM-DD.log`，截图 `logs/shot_*.png`
- 京东 `logs/jd-YYYY-MM-DD.log`，截图 `logs/jd_*.png`

跑完看一眼日志和截图就知道成没成。

## 京东流程细节

```
我的 → 京豆 → 立即刮卡（签到卡）
        ↓
     全部任务 → 逐个「去浏览」，停 6 秒
        ↓
     回到京豆页 → 反复「立即刮卡」把攒到的卡刮完
```

几个踩过的坑（都已处理）：

- **「去刮卡」不是刮卡**：任务列表里那按钮只是跳回京豆页，真正刮卡在那边点「立即刮卡」。
  所以脚本是「先集中做完所有浏览任务，最后回京豆页一次性刮完」
- **刮卡弹窗没有文字按钮**：关闭 X 固定在 `(540, 1916)`，只能按坐标点
- **任务会点不动**：某些任务（如秒杀签到）停 6 秒也不完成，脚本对同一位置最多试 2 次就换下一个
- **不能把「立即领取」当弹窗关**：「我的」页那个「立即领取」是活动入口，点了会跳到活动页

## 每天定时自动运行

用 Windows 任务计划。**推荐用 PowerShell 注册**（比 `schtasks` 稳，
某些安全策略会把 `schtasks.exe` 列入黑名单直接拦掉）。

以管理员身份打开 PowerShell，粘贴执行（淘宝 9:00，京东 9:10，错开避免抢手机）：

```powershell
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# 淘宝 9:00
Register-ScheduledTask -TaskName "Taobao_Taojinbi_Daily" `
  -Action (New-ScheduledTaskAction -Execute "D:\taojinbi\run_taojinbi.bat") `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 09:00) `
  -Settings $settings -Force

# 京东 9:10
Register-ScheduledTask -TaskName "JD_Jingdou_Daily" `
  -Action (New-ScheduledTaskAction -Execute "D:\taojinbi\run_jingdong.bat") `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 09:10) `
  -Settings $settings -Force
```

（把 `D:\taojinbi\` 换成你实际存放本项目的目录）

查看 / 删除：

```powershell
Get-ScheduledTaskInfo -TaskName "Taobao_Taojinbi_Daily"     # 看下次运行时间、上次结果
Get-ScheduledTaskInfo -TaskName "JD_Jingdou_Daily"
Unregister-ScheduledTask -TaskName "Taobao_Taojinbi_Daily" -Confirm:$false   # 删掉
Unregister-ScheduledTask -TaskName "JD_Jingdou_Daily" -Confirm:$false
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
| `taojinbi_adb.py` | 淘宝主脚本：导航 → 补领 → 签到 → 任务 → 领取 |
| `jingdong.py` | 京东主脚本：签到卡 → 浏览任务 → 刮卡（独立，不依赖淘宝脚本）|
| `ocr.ps1` | Windows OCR 封装：输入截图路径，输出「文本 x y」 |
| `run_taojinbi.bat` | 淘宝定时任务入口 |
| `run_jingdong.bat` | 京东定时任务入口 |
| `taojinbi-auto.js` | 备用方案：Hamibot / Auto.js 用的无障碍脚本（如果以后想在手机本地跑）|

## 常见问题

**Q: 点错位置 / 跑一半卡住？**
看 `logs/shot_*.png`（淘宝）或 `logs/jd_*.png`（京东）里最新一张截图，
确认页面停在哪，把卡住的截图和日志发出来对照调整。

**Q: 脚本跑了很久不动？**
`adb` 的 fork 子进程会占住输出管道，导致 `subprocess` 的超时失效、永久阻塞。
京东脚本已经把 adb 输出改成写文件（不经管道），并带 12 分钟总超时看门狗，
到点会自己退出，不会一直挂着。

**Q: OCR 识别不到文字？**
H5 活动页动效多，偶尔整页都识别不出来。脚本会重截 2~3 次；
仍失败才退回上一页。如果反复失败，先手动把手机停在目标页面再跑。

**Q: 任务都显示已完成，脚本会怎样？**
输出「没有可做的任务了」然后正常结束，不会重复点击。

**Q: 换了手机 / 分辨率不一样？**
大部分坐标是 OCR 现场算的，但有几个写死的兜底值需要按新分辨率换算：
淘宝的 `COIN_ICON_OFFSET = 60`、京东的 `BEAN_TILE`、`TAB_MINE`、`SCRATCH_POPUP_X`。

## 风险提示

模拟点击属于灰色地带。淘宝/京东风控严格时理论上存在限流/账号风险；
签到和浏览类任务大量人在用，实际风险很低，但请自行斟酌。
**不要使用网上那些「刷豆软件」**，那种是真的会封号。

京豆有效期约 180 天，记得及时用掉。
