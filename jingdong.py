# -*- coding: utf-8 -*-
"""
京东京豆 · 电脑端 ADB 自动签到 + 刮卡 + 任务（OCR 视觉定位版 v1）

流程：
  1) 京东 → 我的 → 京豆
  2) 点「立即刮卡」领签到卡（弹窗自动关掉）
  3) 进「全部任务」→ 逐个点「去浏览」，停在页面上 6 秒即完成（不用滑动）
  4) 每完成一项，按钮会变成「去刮卡」→ 刮掉 → 关弹窗
  5) 循环到没有可做的任务为止

与淘宝版的关键差异（实测）：
  * 京东浏览任务不需要滑动，停在页面上等倒计时走完即可
  * 奖励是「刮卡次数」，刮开才知道给多少豆
  * 刮卡弹窗没有文字按钮，关闭 X 固定在 (540,1916)（1080x2400 实测）

工程注意：
  * 所有 adb 调用都把 stdout 重定向到文件，不用 PIPE ——
    adb 的 fork 子进程会占住管道，subprocess 的 timeout 会失效导致永久卡死
  * 有 12 分钟总超时看门狗

用法：
  python jingdong.py            执行
  python jingdong.py --dry      只识别不点击
  python jingdong.py --no-task  只刮签到卡，不做任务

日志 logs/jd-YYYY-MM-DD.log，截图 logs/jd_*.png
"""

import os
import sys
import time
import datetime
import subprocess
import threading

import devlink

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
SHOT = os.path.join(TMP, "jd_screen.png")
OCR_OUT = os.path.join(TMP, "jd_ocr.txt")
ADB_OUT = os.path.join(TMP, "jd_adb.txt")

JD = "com.jingdong.app.mall"
DRY = "--dry" in sys.argv
NO_TASK = "--no-task" in sys.argv

LOG_FILE = os.path.join(LOG_DIR, "jd-%s.log" % datetime.date.today().isoformat())

# ---- 坐标（1080x2400 实测，OCR 找不到时兜底）----
TAB_MINE = (971, 2320)          # 底部「我的」
BEAN_TILE = (371, 467)          # 我的页顶部「京豆」格子（第 2 格）
SCRATCH_POPUP_X = (540, 1916)   # 刮卡弹窗左下关闭 X

POPUPS = ("关闭", "跳过", "我知道了", "以后再说", "不感兴趣", "暂不开启")


# ---------------- 基础 ----------------

def log(msg):
    line = "[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def adb_run(args, timeout=60):
    """adb 输出写文件（不用 PIPE，避免 adb fork 出的子进程占住管道导致永久阻塞）"""
    try:
        with open(ADB_OUT, "wb") as f:
            subprocess.run(["adb"] + args, stdout=f, stderr=subprocess.DEVNULL,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        log("    adb 超时: %s" % " ".join(args[:3]))
        return ""
    except Exception as e:
        log("    adb 失败: %s" % e)
        return ""
    try:
        with open(ADB_OUT, "rb") as f:
            return f.read().decode("utf-8", "replace")
    except Exception:
        return ""


def tap(x, y, name=""):
    if name:
        log("  tap(%d,%d) %s" % (x, y, name))
    if DRY:
        return
    adb_run(["shell", "input", "tap", str(int(x)), str(int(y))], timeout=25)


def back(times=1, wait=2.2):
    for _ in range(times):
        adb_run(["shell", "input", "keyevent", "KEYCODE_BACK"], timeout=25)
        time.sleep(wait)


def swipe(down=False, times=1):
    for _ in range(times):
        if down:
            adb_run(["shell", "input", "swipe", "540", "600", "540", "1900", "300"])
        else:
            adb_run(["shell", "input", "swipe", "540", "1600", "540", "1000", "300"])
        time.sleep(0.9)


def scroll_top(times=2):
    swipe(down=True, times=times)


def get_focus():
    txt = adb_run(["shell", "dumpsys", "window"], timeout=30)
    for line in txt.splitlines():
        if "mCurrentFocus" in line and "Window{" in line:
            for p in line.split():
                if "/" in p and "." in p:
                    return p.split("/")[0]
    return ""


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


def screen():
    """截图 + OCR → [(文本, x, y, 'W'|'L', box|None)]"""
    try:
        with open(SHOT, "wb") as f:
            subprocess.run(["adb", "exec-out", "screencap", "-p"],
                           stdout=f, stderr=subprocess.DEVNULL, timeout=60)
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", OCR_PS1, "-ImagePath", SHOT, "-OutFile", OCR_OUT],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    except Exception as e:
        log("  截图/OCR 失败: %s" % e)
        return []

    items = []
    try:
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
    except Exception:
        pass
    return items


def screen_retry(tries=3, min_items=6):
    """OCR 偶尔只认出几行，此时绝不能据此判断页面 → 重截"""
    items = []
    for _ in range(tries):
        items = screen()
        if len(items) >= min_items:
            return items
        time.sleep(1.2)
    return items


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


def label_pos(items, keyword):
    """按字符比例定位关键字（OCR 会把相邻标签合并成一行）"""
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
    src = os.path.join(LOG_DIR, "jd_%s_%s.png"
                       % (datetime.datetime.now().strftime("%m%d_%H%M%S"), tag))
    try:
        with open(SHOT, "rb") as f, open(src, "wb") as g:
            g.write(f.read())
    except Exception:
        pass


# ---------------- 页面判定 ----------------

def is_bean_page(items):
    return bool(find(items, "天天刮京豆", "京豆抵现金", "任务卡"))


def is_task_page(items):
    # 「刮卡次数」只出现在任务列表的每一行；京豆页写的是「刮卡+1」
    return bool(find(items, "刮卡次数", "浏览6s，刮卡"))


def is_mine_page(items):
    return bool(find(items, "优惠券") and find(items, "白条", "我的订单", "京豆"))


def dismiss(items):
    """关掉「关闭/跳过/我知道了」这类有文字的弹窗"""
    for _ in range(3):
        hit = find(items, *POPUPS)
        if not hit:
            return items
        tap(hit[0], hit[1], "关弹窗:" + hit[2])
        time.sleep(2)
        items = screen_retry()
    return items


# ---------------- 导航 ----------------

def ensure_jd():
    for _ in range(3):
        if get_focus() == JD:
            return True
        log("  京东不在前台，重新拉起")
        adb_run(["shell", "monkey", "-p", JD, "-c",
                 "android.intent.category.LAUNCHER", "1"], timeout=40)
        time.sleep(8)
    return get_focus() == JD


def open_bean_page():
    """京东 → 我的 → 京豆"""
    log("[1/4] 进入京豆页")
    if not ensure_jd():
        log("  [X] 拉不起京东")
        return False

    items = screen_retry()
    if is_bean_page(items):
        log("  已经在京豆页")
        return True

    # 退回到「我的」页（京东会恢复上次页面）
    for _ in range(4):
        if is_mine_page(items):
            break
        back(1, 2.2)
        items = dismiss(screen_retry())
        if is_bean_page(items):
            log("  已经在京豆页")
            return True

    if not is_mine_page(items):
        tap(TAB_MINE[0], TAB_MINE[1], "我的tab")
        time.sleep(4)
        items = dismiss(screen_retry())

    if not is_mine_page(items):
        log("  [X] 没回到「我的」页")
        return False

    scroll_top(2)
    time.sleep(1)

    for attempt in range(3):
        tap(BEAN_TILE[0], BEAN_TILE[1], "京豆格子")
        for _ in range(5):
            time.sleep(3)
            items = dismiss(screen_retry())
            if is_bean_page(items):
                log("  已进入京豆页")
                return True
        log("  没进去（第 %d 次），退回重试" % (attempt + 1))
        back(1, 2.2)
        items = dismiss(screen_retry())
        if not is_mine_page(items):
            tap(TAB_MINE[0], TAB_MINE[1], "我的tab")
            time.sleep(4)

    log("  [X] 进不去京豆页")
    return False


def open_all_tasks():
    log("[2/4] 打开全部任务")
    items = dismiss(screen_retry())
    if is_task_page(items):
        return items
    if is_bean_page(items):
        scroll_top(2)
        time.sleep(1)
        items = dismiss(screen_retry())

    hit = find(items, "全部任务")
    if not hit:
        log("  找不到「全部任务」")
        return None

    tap(hit[0], hit[1], "全部任务")
    for _ in range(3):
        time.sleep(3)
        items = dismiss(screen_retry())
        if is_task_page(items):
            return items
    log("  点了「全部任务」但列表没出来")
    return None


def back_to_task_page():
    """回到任务列表；绝不再连着盲按返回键"""
    for _ in range(2):
        items = dismiss(screen_retry())
        if is_task_page(items):
            return items
        if is_bean_page(items):
            scroll_top(2)
            time.sleep(1)
            items = dismiss(screen_retry())
            hit = find(items, "全部任务")
            if hit:
                tap(hit[0], hit[1], "全部任务")
                time.sleep(4)
                continue
            return items
        back(1, 2.2)

    items = dismiss(screen_retry())
    if not is_task_page(items):
        log("  页面丢了，重新导航")
        if open_bean_page():
            return open_all_tasks()
    return items


# ---------------- 刮卡 ----------------

def close_scratch_popup():
    """刮卡结果弹窗没有文字按钮，直接点固定 X；两次还不行按返回"""
    for _ in range(2):
        items = dismiss(screen_retry())
        if is_task_page(items):
            return items
        tap(SCRATCH_POPUP_X[0], SCRATCH_POPUP_X[1], "关闭刮卡弹窗")
        time.sleep(2)
    items = dismiss(screen_retry())
    if not is_task_page(items):
        back(1, 2.2)
        items = dismiss(screen_retry())
    return items


def do_scratch():
    """点「立即刮卡」并关弹窗；没有可刮的返回 False"""
    items = dismiss(screen())
    hit = find(items, "立即刮卡")
    if not hit:
        scroll_top(2)                 # 刮卡按钮在页面顶部，可能被滚走了
        items = dismiss(screen_retry())
        hit = find(items, "立即刮卡")
    if not hit:
        return False
    tap(hit[0], hit[1], "立即刮卡")
    time.sleep(3)
    tap(SCRATCH_POPUP_X[0], SCRATCH_POPUP_X[1], "关闭刮卡弹窗")
    time.sleep(2)
    dismiss(screen_retry())
    return True


def find_button(items, *keywords):
    for kw in keywords:
        hit = label_pos(items, kw)
        if hit:
            return hit
    return None


def find_buttons(items, *keywords):
    """返回所有「去浏览/去完成」按钮，按 y 排序"""
    out = []
    for kw in keywords:
        for it in items:
            if kw in it[0]:
                pos = _char_pos(it, kw) if it[3] == "L" else (it[1], it[2], kw)
                if pos:
                    out.append(pos)
    return sorted(out, key=lambda t: t[1])


def run_tasks():
    log("[3/4] 做任务（每项浏览 6 秒）")
    items = open_all_tasks()
    if not items:
        log("  任务页没打开，跳过")
        return 0

    done = 0
    tried = {}                       # (x,y) 网格 → 已尝试次数，避免死磕点不动的任务
    for _ in range(14):
        devlink.keep_awake(adb_run, log)     # 中途掉线/灭屏就地救一次
        items = back_to_task_page()
        if not items:
            log("  任务页丢失，结束浏览环节")
            break

        cands = find_buttons(items, "去浏览", "去完成", "去参与")
        if not cands:
            for _ in range(2):
                swipe()
                items = dismiss(screen_retry())
                cands = find_buttons(items, "去浏览", "去完成", "去参与")
                if cands:
                    break

        browse = None
        for c in cands:
            key = (c[0] // 40, c[1] // 40)
            if tried.get(key, 0) < 2:      # 同一位置最多试 2 次，点不动就换下一个
                browse = c
                break

        if not browse:
            log("  没有可做的任务了")
            break

        key = (browse[0] // 40, browse[1] // 40)
        tried[key] = tried.get(key, 0) + 1
        tap(browse[0], browse[1], "去浏览")
        time.sleep(8)                 # 停 6 秒就够，多等 2 秒保险
        back_to_task_page()
        done += 1
        log("  完成第 %d 项浏览" % done)

    # 任务列表里的「去刮卡」只是跳回京豆页，真正刮卡在那边做，
    # 所以这里集中收尾：回京豆页 → 滚到顶 → 反复「立即刮卡」
    log("[4/4] 回京豆页刮卡")
    back(1, 2.2)
    items = dismiss(screen_retry())
    if not is_bean_page(items):
        open_bean_page()
    scroll_top(2)
    time.sleep(1)

    n = 0
    while n < 20 and do_scratch():
        n += 1
    log("  刮了 %d 张卡" % n)
    log("  共完成 %d 项浏览" % done)
    return done


def main():
    log("=" * 46)
    # 设备掉线自动重启 adb 服务，灭屏自动唤醒（见 devlink.py）
    if not devlink.prepare(adb_run, log):
        return 2

    if not open_bean_page():
        shot("fail_nav")
        return 3

    shot("bean_page")

    log("  刮签到卡")
    n = 0
    while do_scratch():
        n += 1
        if n >= 5:
            break
    log("  刮了 %d 次签到卡" % n)

    if not NO_TASK:
        try:
            run_tasks()
        except Exception as e:
            log("  任务环节异常: %s" % e)

    shot("final")
    log("结束")
    return 0


def watchdog(minutes=12):
    """总超时保护：万一某步卡死，到点直接退出，保证定时任务不挂在那里"""
    time.sleep(minutes * 60)
    log("[X] 超过 %d 分钟，强制退出" % minutes)
    os._exit(9)


if __name__ == "__main__":
    threading.Thread(target=watchdog, args=(12,), daemon=True).start()
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as e:
        log("崩溃: %s" % e)
        sys.exit(1)
