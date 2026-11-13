# 淘金币 / 京豆 / 东东农场 自动领取（电脑端 ADB + OCR 视觉定位）

用电脑控制安卓手机，每天自动完成**淘宝淘金币**、**京东京豆**和**京东东东农场**的签到、浏览任务与浇水。

不需要在手机上装任何 App（不需要 Hamibot / Auto.js），全程依赖：

- **ADB**：模拟点击、滑动、截屏
- **Windows 自带 OCR**：识别屏幕上的中文文字，按文字定位按钮（不怕 App 改版换坐标）

| 脚本 | 平台 | 每日产出 |
|------|------|----------|
| `taojinbi_adb.py` | 淘宝淘金币 | 签到 120 金币 + 浏览任务（每项 30~60） |
| `jingdong.py` | 京东京豆 | 签到卡 + 浏览任务换刮卡（100 京豆 = 1 元） |
| `jd_farm.py` | 京东东东农场 | 签到 + 浏览任务领水滴 + 自动浇水（约 15~20 天换水果/红包） |

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

浏览任务的计时规则各不一样，这是实现上最大的差别：

| | 淘宝淘金币 | 京东京豆 | 京东东东农场 |
|---|---|---|---|
| 计时方式 | **必须持续滑动**才计时（每 1.2 秒滑一次）| **停在页面**上就倒计时 | 同京豆，停 6 秒 |
| 任务时长 | 15~22 秒/项 | 6 秒/项 | 6 秒/项 |
| 奖励 | 直接到账 | 换成「刮卡次数」，刮开才知道多少 | 换成水滴，要**手动点「去领奖」** |
| 收尾 | 点「领取」 | 回京豆页刮完所有卡 | 用「浇5次」水壶把水滴浇掉 |

农场是 H5 canvas 页面，美术字 OCR 基本认不出，所以主界面按钮用固定坐标 +
OCR 校验页面状态；任务面板是原生列表，OCR 识别很准，按行结构解析。

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

:: 京东东东农场：签到 → 浏览任务领水滴 → 浇水
python jd_farm.py

:: 只识别不点击（调试用）
python taojinbi_adb.py --dry
python jingdong.py --dry
python jd_farm.py --dry

:: 只签到，不做任务
python taojinbi_adb.py --no-task
python jingdong.py --no-task
python jd_farm.py --no-task
```

| 脚本 | 耗时 |
|------|------|
| 淘宝 | 3~5 分钟（每项任务要滑 22 秒）|
| 京东京豆 | 2~4 分钟（每项停 8 秒，比淘宝快）|
| 东东农场 | 3~6 分钟（最多 8 项浏览 + 8 轮浇水）|

**期间不要碰手机**。日志分别写入：

- 淘宝 `logs/YYYY-MM-DD.log`，截图 `logs/shot_*.png`
- 京东京豆 `logs/jd-YYYY-MM-DD.log`，截图 `logs/jd_*.png`
- 东东农场 `logs/farm-YYYY-MM-DD.log`，截图 `logs/farm_*.png`

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

## 东东农场流程细节

```
京东搜索深链（keyword=东东农场）→ 直接进农场
        ↓
  关弹窗 / 选奖品档位 → 签到
        ↓
 「领水滴」面板 → 只做描述含「浏览6秒」的任务，停 9 秒返回
        ↓
  按钮变「去领奖」→ 点掉领水滴 → 循环
        ↓
  关面板 → 反复点右下「浇5次」水壶，直到水滴不足或浇不动
        ↓
  回面板把「每日累计浇水20次」等奖领掉
```

几个实测要点：

- **入口用深链**：`我的 → 互动游戏` 里翻不到农场，而且 ADB 没法直接输入中文。
  京东对搜索词「东东农场」做了活动直达，用 `am start -d` 打开这个 URL 就能进
- **首次要选奖品档位**：新一轮种植会弹「7天 / 15天 / 30天」三档，脚本默认选第一个
  「最快收获 7 天」。想换档改 `jd_farm.py` 的 `PRIZE_CHOICE`（1/2/3）；
  也可以在农场页面里自己更换奖品
- **只做「浏览6秒」类任务**：面板里还有「去百度极速版领现金」「去开启定时领水通知」
  「京东直播」等任务，会跳外部 App、系统设置或直播间，很容易回不到农场。
  脚本按每行的描述行过滤，非浏览类一律跳过（`SKIP_WORDS` 是第二道保险）
- **完成≠到账**：浏览完按钮变成「去领奖」，必须点一下才拿到水滴；
  所以脚本每轮循环都会先把所有「去领奖」点掉
- **弹窗特别多**：选奖品、引导气泡、限时任务、浇水升级福利、中奖红包、
  「浏览6秒」任务浮层……都是纯图片无文字关闭按钮，脚本按特征文案 + 固定 X 坐标处理。
  浮层不关掉会挡住水壶，导致后面浇水全在空转
- **浇水有停滞保护**：如果连续两轮水滴数量不下降，说明被弹窗挡住或浇不动了，
  直接停止，不空耗
- **水滴会过期**：农场公告写「连续 7 天不浇水，所有水滴会在第 8 天 0 点过期」，
  所以**每天浇一次比攒水滴更重要**

## 每天定时自动运行

用 Windows 任务计划。三个任务都带**随机延迟**，每天不在同一分钟动手
（`RandomDelay` 是任务计划自带的能力：到点后系统在窗口内随机挑一个时刻启动，
所以不用改脚本、也不会因为脚本多睡几分钟占着控制台）：

| 任务 | 触发时刻 | 随机范围 | 实际执行窗口 |
|------|----------|----------|--------------|
| `Taobao_Taojinbi_Daily` | 08:10 | `PT18M` | 08:10 ~ 08:28 |
| `JD_Jingdou_Daily` | 09:01 | `PT3M` | 09:01 ~ 09:04 |
| `JD_Farm_Daily` | 09:20 | 无 | 09:20 |

**推荐用 PowerShell 注册**（比 `schtasks` 稳，某些安全策略会把 `schtasks.exe` 列入黑名单直接拦掉）。

先建三个每天固定时刻的任务：

```powershell
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# 淘宝 08:10 / 京豆 09:01 / 农场 09:20，错开避免抢同一部手机
Register-ScheduledTask -TaskName "Taobao_Taojinbi_Daily" `
  -Action (New-ScheduledTaskAction -Execute "D:\taojinbi\run_taojinbi.bat") `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 08:10) `
  -Settings $settings -Force

Register-ScheduledTask -TaskName "JD_Jingdou_Daily" `
  -Action (New-ScheduledTaskAction -Execute "D:\taojinbi\run_jingdong.bat") `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 09:01) `
  -Settings $settings -Force

Register-ScheduledTask -TaskName "JD_Farm_Daily" `
  -Action (New-ScheduledTaskAction -Execute "D:\taojinbi\run_jdfarm.bat") `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 09:20) `
  -Settings $settings -Force
```

`New-ScheduledTaskTrigger` 不支持随机延迟，得改一次 XML 再注册：

```powershell
function Add-RandomDelay($name, $start, $delay) {
  $xml = Export-ScheduledTask -TaskName $name
  $xml = $xml -replace '<StartBoundary>[^<]+</StartBoundary>', "<StartBoundary>$start</StartBoundary>"
  $xml = $xml -replace '(<StartBoundary>[^<]+</StartBoundary>)', "`$1`r`n      <RandomDelay>$delay</RandomDelay>"
  Register-ScheduledTask -Xml $xml -TaskName $name -Force
}

Add-RandomDelay "Taobao_Taojinbi_Daily" "2026-11-13T08:10:00+08:00" "PT18M"
Add-RandomDelay "JD_Jingdou_Daily"      "2026-11-13T09:01:00+08:00" "PT3M"
```

`StartBoundary` 的日期部分不影响每日重复，只取时分。校验结果：

```powershell
foreach ($n in "Taobao_Taojinbi_Daily","JD_Jingdou_Daily") {
  (Export-ScheduledTask -TaskName $n) -split "`n" | Select-String "StartBoundary|RandomDelay"
  (Get-ScheduledTaskInfo -TaskName $n).NextRunTime     # 这个时间已经含随机结果
}
```

想调窗口只改 `PT18M`（18 分钟）这个值：`PT6M` 就是 6 分钟窗口。
随机延迟不算进 `ExecutionTimeLimit`，30 分钟的执行上限仍然从真正启动那刻算。

（把 `D:\taojinbi\` 换成你实际存放本项目的目录）

查看 / 删除：

```powershell
Get-ScheduledTask -TaskName "Taobao_Taojinbi_Daily","JD_Jingdou_Daily","JD_Farm_Daily" |
  ForEach-Object { $i = Get-ScheduledTaskInfo -TaskName $_.TaskName;
    "{0,-24} {1,-8} next={2} result={3}" -f $_.TaskName, $_.State, $i.NextRunTime, $i.LastTaskResult }

Unregister-ScheduledTask -TaskName "Taobao_Taojinbi_Daily" -Confirm:$false   # 删掉
Unregister-ScheduledTask -TaskName "JD_Jingdou_Daily" -Confirm:$false
Unregister-ScheduledTask -TaskName "JD_Farm_Daily" -Confirm:$false
```

**注意**：

- 手机要保持插着 USB 且 ADB 授权有效
- 手机必须是解锁状态；设了锁屏密码的话脚本叫不醒它，
  需要把锁屏去掉或改为无密码
- 如果电脑当时关机/睡眠，`StartWhenAvailable` 会在开机后补跑一次
- 三个任务合计约 10~15 分钟，期间不要碰手机；三个时间点错开是为了不抢同一部手机的 ADB
- 随机延迟只改启动时刻，跑的内容完全一样，不影响收益
- 设备掉线或手机灭屏，脚本自己会救（见下一节），不用手动干预

## 手机掉线 / 灭屏的自愈

无人值守跑定时任务，最常见的两种失败是「adb 里没有设备」和「手机灭屏截图全黑」。
三个脚本启动时都会先走 `devlink.py` 的 `prepare()`：

| 现象 | 处理 |
|------|------|
| `adb devices` 里没有设备 / 状态为 `offline` | 停服务（`adb kill-server`）→ 起服务（`adb start-server`）→ 等重连，最多 3 轮 |
| 设备在但 `mWakefulness=Asleep` | `KEYCODE_WAKEUP` + `dismiss-keyguard`，再回读 `dumpsys power` 确认真的亮了 |
| 长流程中途掉线或灭屏 | 每 90 秒检查一次（`keep_awake()`），就地重启服务 + 唤醒 |

日志里会看到：

```
[0/4] 连接手机
  adb 停服务
  adb 起服务
  设备已恢复: m7zphmemnnojojuk
  屏幕没亮，唤醒（第 1 次）
```

实测结论（这台小米 2312DRAABC）：

- **只重启 adb 服务不会让手机亮屏**，设备会重新连上，但状态还是 `Asleep`，
  所以唤醒必须单独做（`input keyevent KEYCODE_WAKEUP`）
- 唤醒后 `wm dismiss-keyguard` 就能到桌面，没设锁屏密码时不需要额外上滑
- 手机灭屏时 adb 仍然可用，只是截图全黑——这是以前脚本"莫名失败"的主要原因

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
- **定时任务防误杀**：计划任务跑在共享控制台里，外部控制台事件（`CTRL_C_EVENT`）
  会把脚本当成手动 Ctrl+C 杀掉。三个脚本在非交互环境（`stdin` 不是终端）默认忽略
  SIGINT，手动在命令行跑时 Ctrl+C 仍然有效

## 文件说明

| 文件 | 作用 |
|------|------|
| `taojinbi_adb.py` | 淘宝主脚本：导航 → 补领 → 签到 → 任务 → 领取 |
| `jingdong.py` | 京东主脚本：签到卡 → 浏览任务 → 刮卡（独立，不依赖淘宝脚本）|
| `jd_farm.py` | 东东农场主脚本：签到 → 浏览任务领水滴 → 浇水（复用 `jingdong.py` 基础层）|
| `devlink.py` | 设备自愈：掉线重启 adb 服务、灭屏自动唤醒（三个脚本共用）|
| `ocr.ps1` | Windows OCR 封装：输入截图路径，输出「文本 x y」 |
| `run_taojinbi.bat` | 淘宝定时任务入口 |
| `run_jingdong.bat` | 京东京豆定时任务入口 |
| `run_jdfarm.bat` | 东东农场定时任务入口 |
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

**Q: 农场脚本跑得很快、没做任务就结束了？**
多半是当天的浏览任务已经做完了，或者首轮选奖品后任务列表还没刷新。
看 `logs/farm-*.log`：出现「没有可做的浏览任务了」就是正常收尾，
第二天定时任务会重新做。想手动重跑用 `python jd_farm.py`。

**Q: 农场浇水只浇了两轮就停？**
这是保护逻辑：连续两轮水滴数不下降，说明被浮层挡住或当天浇水已到上限，
脚本会主动停止而不是空转 8 轮。看最新 `logs/farm_*.png` 截图确认页面状态。

**Q: 定时任务没跑成功，日志里是「没有设备连接」？**
脚本已经自己重启过 adb 服务三次还拿不到设备，说明是物理层断了：
数据线松了、手机没电关机、或插在电脑的充电口（不传数据）。
插好线后 `adb devices` 能看到设备再手动补跑一次即可。

**Q: 换了手机 / 分辨率不一样？**
大部分坐标是 OCR 现场算的，但有几个写死的兜底值需要按新分辨率换算：
淘宝的 `COIN_ICON_OFFSET = 60`、京东的 `BEAN_TILE`、`TAB_MINE`、`SCRATCH_POPUP_X`；
农场因为整个主界面是 canvas、OCR 认不出美术字，写死的坐标更多
（`WATER_POT`、`SIGN_ENTRY`、`TASK_ENTRY`、几个弹窗 X），换分辨率要按
`jd_farm.py` 顶部常量逐一换算。

## 风险提示

模拟点击属于灰色地带。淘宝/京东风控严格时理论上存在限流/账号风险；
签到和浏览类任务大量人在用，实际风险很低，但请自行斟酌。
**不要使用网上那些「刷豆软件」**，那种是真的会封号。

京豆有效期约 180 天，记得及时用掉。

农场的新一轮种植需要选奖品档位，脚本默认选「最快收获 7 天」那一档
（`jd_farm.py` 的 `PRIZE_CHOICE`）；如果你想要别的水果/日用品，
先自己在农场里换好，或改这个配置。
