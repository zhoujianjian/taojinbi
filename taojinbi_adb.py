# -*- coding: utf-8 -*-
"""
淘宝淘金币 · 电脑端 ADB 自动签到 + 做任务（OCR 视觉定位版 v4）

流程：
  1) 唤醒手机 → 回到淘宝主界面
  2) 进入「淘金币」页
  3) 补领「昨日未领」，点「签到」
  4) 点「去赚金币」→ 今日速赚面板 → 按行扫描逐项做任务
  5) 领取页面上出现的「领取」奖励

关键实现：
  * 浏览类任务必须"持续滑动"才会计时 → dwell() 每 1.2 秒滑一次
  * 任务完成以页面顶部文案为准（已得/任务完成/已完成…）→ browse_task()
  * 跳过会跳转支付宝的任务（蚂蚁庄园/支付宝农场/蚂蚁森林）和答题类任务
  * 任务名称会轮换（如"精致面霜"→"搜一搜你心仪的宝贝"），所以按面板行结构识别，不认名字

用法：
  python taojinbi_adb.py            执行
  python taojinbi_adb.py --dry      只识别不点击
  python taojinbi_adb.py --no-task  只签到，不做任务

日志 logs/YYYY-MM-DD.log，截图 logs/shot_*.png
"""

import os
import sys
import time
import datetime
import subprocess

import devlink

# 关键：控制台/重定向到文件时避免 GBK 编码崩溃
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE, "logs")
TMP = os.path.join(BASE, "_tmp")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(TMP, exist_ok=True)

OCR_PS1 = os.path.join(BASE, "ocr.ps1")
SHOT = os.path.join(TMP, "screen.png")
OCR_OUT = os.path.join(TMP, "ocr.txt")

DRY = "--dry" in sys.argv
NO_TASK = "--no-task" in sys.argv

POPUPS = ["关闭", "跳过", "我知道了", "以后再说", "暂不开启", "不感兴趣", "取消"]

# 淘宝活动弹窗没有文字可点的关闭按钮，X 固定在下半屏中部（1080x2400 实测）
POPUP_KEYS = ["PK赛", "开始啦", "去赢取", "加抵金", "立即参与", "恭喜", "领取成功"]
POPUP_CLOSE_XY = (533, 1790)

# 浏览任务完成后页面顶部的提示文案（用于判断是否真的完成，而不是死等时间）
DONE_MARKS = ["已得", "任务完成", "已完成", "已到账", "已领取", "下个任务", "金币已到账"]


def swipe_up(times=1, dist=700, dur=350):
    for _ in range(times):
        adb("shell", "input", "swipe", "540", "1800", "540", str(1800 - dist), str(dur))
        time.sleep(1.2)


def scroll_top(times=3):
    """把当前页滚回顶部（淘宝会记住上次的滚动位置）"""
    for _ in range(times):
        adb("shell", "input", "swipe", "540", "600", "540", "1900", "300")
        time.sleep(0.9)


def dwell(seconds):
    """浏览计时：必须持续滑动才会累计（实测间隔 1.2 秒、短距离滑动有效）"""
    log("    停留 %d 秒（持续滑动计时）" % seconds)
    end = time.time() + seconds
    while time.time() < end:
        adb("shell", "input", "swipe", "540", "1600", "540", "1100", "250")
        time.sleep(1.0)


def browse_task(name, seconds):
    """滑动浏览 + 检测页面顶部"已得/任务完成"提示，未完成则补时间"""
    log("  任务：%s" % name)
    dwell(seconds)
    items = screen()
    hit = find(items, *DONE_MARKS)
    if hit:
        log("    [完成] 检测到提示：%s" % hit[2])
        return True

    log("    未检测到完成提示，再补 10 秒")
    dwell(10)
    items = screen()
    hit = find(items, *DONE_MARKS)
    if hit:
        log("    [完成] 检测到提示：%s" % hit[2])
        return True

    log("    [未确认] 没看到完成提示，可能页面改版或停留不够")
    return False


# ---------------- 基础 ----------------

def log(msg):
    line = "[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with open(os.path.join(LOG_DIR, datetime.date.today().isoformat() + ".log"),
                  "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def adb(*args, timeout=30):
    try:
        r = subprocess.run(["adb"] + list(args), capture_output=True, timeout=timeout)
        return r.stdout.decode("utf-8", "ignore")
    except Exception as e:
        log("adb fail %s: %s" % (args, e))
        return ""


def adb_list(args, timeout=30):
    """给 devlink 用的列表式入口（设备自愈模块统一按 run([...]) 调用）"""
    return adb(*args, timeout=timeout)


def tap(x, y, name=""):
    if DRY:
        log("  [dry] tap(%d,%d) %s" % (x, y, name))
        return
    adb("shell", "input", "tap", str(int(x)), str(int(y)))
    log("  tap(%d,%d) %s" % (x, y, name))
    time.sleep(0.6)


def back(times=1, wait=2.5):
    for _ in range(times):
        adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(wait)


def screen():
    """截图 + OCR → [(文本, x, y, 'W'|'L', box|None)]"""
    try:
        data = subprocess.run(["adb", "exec-out", "screencap", "-p"],
                              capture_output=True, timeout=40).stdout
        with open(SHOT, "wb") as f:
            f.write(data)
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", OCR_PS1, "-ImagePath", SHOT, "-OutFile", OCR_OUT],
                       capture_output=True, timeout=90)
    except Exception as e:
        log("截图/OCR 失败: %s" % e)
        return []
    items = []
    if os.path.exists(OCR_OUT):
        with open(OCR_OUT, encoding="utf-8") as f:
            for ln in f:
                p = ln.rstrip("\n").split("\t")
                try:
                    if len(p) == 6 and p[0] == "L":
                        box = (int(p[2]), int(p[3]), int(p[4]), int(p[5]))
                        items.append((p[1].replace(" ", ""), box[0] + box[2] // 2,
                                      box[1] + box[3] // 2, "L", box))
                    elif len(p) >= 4 and p[0] == "W":
                        items.append((p[1].replace(" ", ""), int(p[2]), int(p[3]), "W", None))
                except ValueError:
                    pass
    return items


def _char_pos(item, keyword):
    text, _, _, _, box = item
    if not box or not text:
        return None
    idx = text.find(keyword)
    if idx < 0:
        return None
    x0, y0, w, h = box
    n = len(text)
    return (x0 + int((idx + len(keyword) / 2.0) / n * w), y0 + h // 2, keyword)


def find(items, *keywords):
    for kind in ("W", "L"):
        for it in items:
            if it[3] != kind:
                continue
            for kw in keywords:
                if kw in it[0]:
                    if kind == "W":
                        return (it[1], it[2], kw)
                    pos = _char_pos(it, kw)
                    if pos:
                        return pos
    return None


def find_all(items, keyword):
    """返回所有匹配（文本, x, y），按 y 排序"""
    out = []
    for it in items:
        if keyword in it[0]:
            if it[3] == "W":
                out.append((it[0], it[1], it[2]))
            else:
                pos = _char_pos(it, keyword)
                if pos:
                    out.append((it[0], pos[0], pos[1]))
    return sorted(out, key=lambda t: t[2])


def label_pos(items, keyword):
    """按字符比例定位关键字位置。
    OCR 会把相邻图标标签合并成一行（如「芭芭农场领淘金币」），
    直接用整行中心会点偏，必须按字符占比算。"""
    for it in items:
        if it[3] == "L" and keyword in it[0]:
            pos = _char_pos(it, keyword)
            if pos:
                return pos
    for it in items:
        if it[3] == "W" and keyword in it[0]:
            return (it[1], it[2], keyword)
    return None


def shot(tag):
    src = os.path.join(LOG_DIR, "shot_%s_%s.png"
                       % (datetime.datetime.now().strftime("%m%d_%H%M%S"), tag))
    try:
        with open(SHOT, "rb") as f, open(src, "wb") as g:
            g.write(f.read())
    except Exception:
        pass


def dismiss(items):
    """关弹窗：先找带文字的关闭/跳过；全屏广告页用返回键关（不再盲点固定坐标，容易点进直播间）"""
    for _ in range(4):
        hit = find(items, *POPUPS)
        if hit:
            tap(hit[0], hit[1], "关弹窗:" + hit[2])
            time.sleep(2)
            items = screen()
            continue

        popup = find(items, *POPUP_KEYS)
        # 只有「看不到页面主体」时才当成真弹窗，避免把页面正文里的活动文案误判
        covered = not (is_coin_page(items) or is_task_panel(items) or find(items, "我的淘宝", "首页"))
        if popup and covered:
            log("    疑似全屏活动弹窗（%s），按返回键关闭" % popup[2])
            adb("shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(2.5)
            items = screen()
            continue
        return items
    return items


def is_coin_page(items):
    return bool(find(items, "赚更多金币", "明日领", "回日常版", "后天", "今天", "去赚金币"))


def is_task_panel(items):
    return bool(find(items, "今日速赚", "完成下方任务", "任务面板"))


# ---------------- 各步骤 ----------------

COIN_ICON_OFFSET = 60          # 「领淘金币」图标在文字标签上方约 60px


def open_coin_page():
    log("[1/5] 回到淘宝并进入淘金币页")
    ensure_taobao()
    items = dismiss(screen())
    if is_coin_page(items):
        log("  已经在淘金币页")
        scroll_top()
        return True

    for attempt in range(4):
        if is_task_panel(items):          # 上次残留的任务面板，先关掉
            back(1, 2)
            items = dismiss(screen())
            continue

        hit = label_pos(items, "领淘金币")
        if hit:
            tap(hit[0], hit[1] - COIN_ICON_OFFSET, "领淘金币图标")
            for _ in range(6):            # 淘金币页加载慢，最多等 18 秒
                time.sleep(3)
                items = dismiss(screen())
                if is_coin_page(items):
                    log("  已进入淘金币页")
                    scroll_top()
                    time.sleep(1)
                    return True
            log("  点了图标没进去，重试")
            continue

        my = find(items, "我的淘宝")
        if my:
            tap(my[0], my[1], "我的淘宝tab")
        else:
            back(1, 2.5)
        time.sleep(4)
        items = dismiss(screen())
        if is_coin_page(items):
            log("  已进入淘金币页")
            scroll_top()
            time.sleep(1)
            return True

    log("  [X] 没进到淘金币页")
    return False


def claim_yesterday_and_sign():
    log("[2/5] 补领昨日 / 签到")
    items = dismiss(screen())

    hit = find(items, "昨日未领")
    if hit:
        tap(hit[0], hit[1], "昨日未领")
        time.sleep(4)
        items = dismiss(screen())
        log("  已补领昨日金币")
    else:
        log("  没有「昨日未领」")

    hit = find(items, "回日常版")
    if hit:
        tap(hit[0], hit[1], "回日常版")
        time.sleep(4)
        items = dismiss(screen())

    hit = find(items, "签到")
    if hit and hit[1] < 1300:          # 签到区在页面上半部分，避免误点「红包签到」
        tap(hit[0], hit[1], "签到")
        time.sleep(4)
        dismiss(screen())
        log("  已签到")
        return True

    if find(items, "明天", "明日领"):
        log("  今天已签过")
    return False


TASK_ENTRY = ("赚更多金币", "去赚金币", "赚金币", "快速赚", "赚能量")


def open_task_panel():
    ensure_taobao()
    items = dismiss(screen())
    if is_task_panel(items):
        return items
    scroll_top(2)                     # 入口按钮在页面顶部
    items = dismiss(screen())

    for attempt in range(3):
        hit = None
        for kw in TASK_ENTRY:
            hit = label_pos(items, kw)
            if hit:
                break
        if hit:
            tap(hit[0], hit[1], "任务入口:" + hit[2])
            time.sleep(5)
            items = dismiss(screen())
            if is_task_panel(items):
                return items
            log("  点了「%s」但没打开任务面板" % hit[2])
        else:
            log("  页面上没有任务入口文案")

        if attempt == 0:
            open_coin_page()          # 可能不在淘金币页，重新进
            items = dismiss(screen())
        elif attempt == 1:
            back(1, 2.5)
            items = dismiss(screen())

    log("  找不到任务面板入口")
    return None


def panel_home(items):
    """把任务面板滚回顶部（面板记住上次位置，否则前几项看不到）"""
    for _ in range(2):
        adb("shell", "input", "swipe", "540", "900", "540", "1700", "300")
        time.sleep(1.0)
    time.sleep(1.5)
    return dismiss(screen())


def parse_tasks(items):
    """从任务面板解析出 [(徽章y, 徽章x, 任务标题)]，不依赖任务名（名称会轮换）"""
    badges = [(x, y) for (text, x, y, kind, box) in items
              if kind == "L" and x >= 880 and text.startswith("+")]
    rows = []
    for bx, by in badges:
        if by < 620:              # 顶部的 +150 额外奖励不是任务行
            continue
        above = [(y, text) for (text, x, y, kind, box) in items
                 if kind == "L" and 0 < by - y < 140 and text.strip("0123456789+/ ")]
        if not above:
            continue
        above.sort(reverse=True)          # 取紧贴徽章上方的那一行（任务标题）
        title = above[0][1]
        if title in ("淘金币", "额外得", "今日速赚", "完成下方任务得额外金币"):
            continue
        rows.append((by, bx, title))
    return sorted(rows)


SKIP_WORDS = ("支付宝", "蚂蚁", "趣味课堂", "答题", "搜一搜",
              "任务到访", "每日来任务面板")   # 支付宝跳转 / 答题 / 搜索 / 面板说明行，不做
CLAIM_BAN = ("免费领取", "试用领取", "去领取", "领券", "领取红包",
             "领取权益", "领取使用", "领取优惠")


def run_tasks():
    log("[3/5] 做今日任务")
    if not open_task_panel():
        log("  任务面板没打开，跳过")
        return 0
    shot("task_panel")

    done = 0
    count = {}
    miss = 0
    for _ in range(9):
        items = open_task_panel()
        if not items:
            miss += 1
            if miss == 1:
                log("  面板打不开，重新进入淘金币页再试")
                open_coin_page()
            else:
                log("  面板连续打不开，结束任务环节")
                break
            continue
        miss = 0
        items = panel_home(items)

        target = None
        for page in range(3):        # 面板可能停在任意滚动位置，逐页扫描
            for by, bx, title in parse_tasks(items):
                if any(w in title for w in SKIP_WORDS):
                    continue
                if "2/2" in title or "已完成" in title or "已领" in title:
                    continue
                key = title[:6]
                if count.get(key, 0) >= 2:
                    continue
                target = (by, bx, title, key)
                break
            if target:
                break
            adb("shell", "input", "swipe", "540", "1600", "540", "1000", "300")
            time.sleep(1.5)
            items = dismiss(screen())

        if not target:
            log("  没有可做的任务了")
            break

        by, bx, title, key = target
        tap(bx, by + 6, "任务:" + title[:12])
        time.sleep(3)
        browse_task(title[:12], 22)
        back(2, 2.5)
        count[key] = count.get(key, 0) + 1
        done += 1
        time.sleep(2)

    log("  完成 %d 次任务浏览" % done)
    return done


def get_focus_package():
    txt = adb("shell", "dumpsys", "window")
    for line in txt.splitlines():
        if "mCurrentFocus" in line and "Window{" in line:
            parts = line.split()
            for p in parts:
                if "/" in p and "." in p:
                    return p.split("/")[0]
    return ""


def ensure_taobao(max_back=4):
    """确保回到淘宝前台（做任务会跳支付宝等外部 App）"""
    for _ in range(max_back + 1):
        pkg = get_focus_package()
        if pkg == "com.taobao.taobao":
            return True
        log("  当前在 %s，返回淘宝" % (pkg or "unknown"))
        back(1, 2.5)
    pkg = get_focus_package()
    if pkg != "com.taobao.taobao":
        adb("shell", "monkey", "-p", "com.taobao.taobao",
            "-c", "android.intent.category.LAUNCHER", "1")
        time.sleep(8)
    return get_focus_package() == "com.taobao.taobao"


def claim_rewards():
    log("[4/5] 领取奖励")
    claimed = 0
    last = None
    repeat = 0
    for _ in range(8):
        items = dismiss(screen())
        # 只在淘金币页/任务面板里领，避免点到首页广告的「免费领取」跳到别处
        if not (is_coin_page(items) or is_task_panel(items)):
            log("  不在淘金币页，跳过领取")
            break
        hit = None
        for it in items:
            text = it[0]
            if "领取" not in text:
                continue
            if any(b in text for b in CLAIM_BAN):
                continue
            hit = (text, it[1], it[2])
            break
        if not hit:
            break
        # 同一坐标连续命中说明点不动，直接停
        key = (hit[1] // 20, hit[2] // 20)
        repeat = repeat + 1 if key == last else 1
        last = key
        if repeat >= 3:
            log("  同一位置重复命中，停止")
            break
        tap(hit[1], hit[2], "领取:" + hit[0][:8])
        claimed += 1
        time.sleep(3)
    log("  领取 %d 个" % claimed)
    return claimed


def main():
    log("=" * 46)
    # 设备掉线自动重启 adb 服务，灭屏自动唤醒（见 devlink.py）
    if not devlink.prepare(adb_list, log):
        return 2

    if not open_coin_page():
        shot("fail_nav")
        return 3

    shot("coin_page")
    claim_yesterday_and_sign()

    if not NO_TASK:
        try:
            run_tasks()
        except Exception as e:
            log("  任务环节异常: %s" % e)

    try:
        claim_rewards()
    except Exception as e:
        log("  领取环节异常: %s" % e)

    shot("final")
    log("[5/5] 结束")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as e:
        log("崩溃: %s" % e)
        sys.exit(1)
