# -*- coding: utf-8 -*-
"""
京东「东东农场」· 电脑端 ADB 自动签到 + 领水滴任务 + 浇水（OCR 视觉定位版 v1）

实测界面（1080x2400）：
  * 入口：京东搜索深链 keyword=东东农场 会直接跳进农场 BabelActivity
  * 首次进入会弹「请选择奖品」档位；另有引导气泡、限时任务弹窗、浇水升级福利弹窗
  * 主界面四个底部入口：签到 / 邀请 / 领水滴 / 浇5次水壶（右下）
  * 「领水滴」面板每行右侧按钮：去完成 / 逛一逛 → 浏览 6 秒 → 回来变「去领奖」
  * 「浇5次」水壶点一次浇 5 下，消耗 50g 水滴（10g/次），右下角数字是水滴总量
  * 农场是 H5 canvas 页面，OCR 认不出大部分美术字，所以关键按钮用固定坐标 +
    OCR 校验页面状态（本机分辨率固定，比猜文字可靠）；任务面板是原生列表，OCR 很准

工程注意：
  * 复用 jingdong.py 的基础层（adb 输出写文件、不用 PIPE，避免 fork 子进程占管道卡死）
  * 独立的截图/OCR/adb 临时文件与日志，不和京豆脚本抢文件
  * 15 分钟总超时看门狗

用法：
  python jd_farm.py            执行
  python jd_farm.py --dry      只识别不点击
  python jd_farm.py --no-task  只签到 + 浇水，不做浏览任务

日志 logs/farm-YYYY-MM-DD.log，截图 logs/farm_*.png
"""

import os
import re
import sys
import signal
import time
import datetime
import threading

import jingdong as base
import devlink

# 计划任务在共享控制台里跑，外部控制台事件（CTRL_C_EVENT）会误杀脚本。
# 非交互环境下忽略 SIGINT，保证每天定时跑完；手动 Ctrl+C 仍可中断。
try:
    if not sys.stdin.isatty():
        signal.signal(signal.SIGINT, signal.SIG_IGN)
except Exception:
    pass

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(ROOT, "_tmp")
LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(TMP, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# 和京豆脚本隔离，避免两个定时任务万一重叠时互相覆盖
base.SHOT = os.path.join(TMP, "farm_screen.png")
base.OCR_OUT = os.path.join(TMP, "farm_ocr.txt")
base.ADB_OUT = os.path.join(TMP, "farm_adb.txt")
base.LOG_FILE = os.path.join(LOG_DIR, "farm-%s.log" % datetime.date.today().isoformat())

log = base.log
tap = base.tap
back = base.back
find = base.find
screen = base.screen_retry

JD = base.JD
DRY = base.DRY
NO_TASK = "--no-task" in sys.argv

# 搜索深链：京东对「东东农场」做了活动直达，比从「我的 → 互动游戏」翻找稳
FARM_URL = "https://so.m.jd.com/ware/search.action?keyword=%E4%B8%9C%E4%B8%9C%E5%86%9C%E5%9C%BA"

# ---- 固定坐标（1080x2400 实测）----
PRIZE_BTNS = [(781, 915), (781, 1323), (781, 1730)]  # 选奖品：7天 / 15天 / 30天
PRIZE_CHOICE = 1              # 默认选第一个「最快收获 7 天」，想换档改这里
GUIDE_X = (1000, 318)         # 顶部「可在…里查看」蓝色引导气泡的 X
TASK_POPUP_X = (540, 1700)    # 「去首页点击东东农场」限时任务弹窗的 X
PANEL_CLOSE_X = (990, 395)    # 「做任务领水滴」面板右上角 X
WIN_POPUP_X = (990, 489)      # 浇水中奖弹窗「恭喜中奖啦」右上角 X
TASK_POPUP_FLOAT_X = (944, 715)  # 「浏览6秒 奖励10g 去完成」任务浮层右上角 X
WATER_POT = (911, 1620)       # 右下「浇5次」水壶
SIGN_ENTRY = (127, 1671)      # 「签到」
TASK_ENTRY = (489, 1674)      # 「领水滴」

# 这些任务会跳外部 App / 加桌面组件 / 玩小游戏 / 跳首页回不来，一律不做
# 更根本的过滤：只做描述里写着「浏览6秒」的任务（见 parse_rows / do_tasks）
SKIP_WORDS = ("快手", "极速版", "百度", "小组件", "Joy", "旅行", "首页点击",
              "通知", "直播", "外卖", "小说", "领现金", "邀请", "下单", "开通", "拼团")

MAX_BROWSE = 8                # 单次最多做几个浏览任务（每个约 25 秒）
MAX_WATER_ROUND = 8           # 单次最多点几轮「浇5次」

# 已完成任务有两种文案：「去领奖」和「领奖励」，都要能领
CLAIM_BTNS = ("去领奖", "领奖励")
PANEL_BTNS = CLAIM_BTNS + ("去完成", "逛一逛", "去浇水", "去领取")


def shot(tag):
    src = os.path.join(LOG_DIR, "farm_%s_%s.png"
                       % (datetime.datetime.now().strftime("%m%d_%H%M%S"), tag))
    try:
        with open(base.SHOT, "rb") as f, open(src, "wb") as g:
            g.write(f.read())
    except Exception:
        pass


# ---------------- 页面判定 ----------------

def is_farm(items):
    return bool(find(items, "东东农场"))


def is_task_panel(items):
    return bool(find(items, "做任务领水滴"))


def is_prize_popup(items):
    return bool(find(items, "请选择奖品"))


def read_water(items):
    """右下角水滴总量，OCR 常识别成 '280g'，也可能和别的字粘连；读不到返回 None"""
    for text, x, y, kind, box in items:
        if not (x > 780 and 1500 < y < 1820):
            continue
        m = re.search(r"(\d{2,6})g", text.replace(" ", ""))
        if m:
            return int(m.group(1))
    return None


# ---------------- 弹窗 ----------------

def dismiss(items, rounds=4):
    """农场弹窗很多，按特征逐个清掉；只在没认出主界面时才动「关闭」类文字"""
    for _ in range(rounds):
        if is_prize_popup(items):
            tap(PRIZE_BTNS[PRIZE_CHOICE - 1][0], PRIZE_BTNS[PRIZE_CHOICE - 1][1],
                "选奖品档位 %d" % PRIZE_CHOICE)
            time.sleep(3)
            items = screen()
            continue

        hit = find(items, "开心收下", "收下", "知道了")
        if hit:
            tap(hit[0], hit[1], "收下:" + hit[2])
            time.sleep(2)
            items = screen()
            continue

        # 浇水会随机中红包，弹窗是纯图片，关闭 X 没有文字
        if find(items, "恭喜中奖", "中奖啦", "买买买", "浇水次数达到"):
            tap(WIN_POPUP_X[0], WIN_POPUP_X[1], "关中奖弹窗")
            time.sleep(2)
            items = screen()
            continue

        # 「浏览6秒 奖励10g / 去完成」任务浮层：会挡住水壶，必须关掉
        # 用「去完成」按钮的 x 区分：浮层按钮在屏幕中间(≈540)，任务面板在右侧(≈932)
        float_btn = [it for it in items
                     if it[3] == "L" and "去完成" in it[0] and 400 < it[1] < 700]
        if float_btn and find(items, "浏览6秒", "奖励"):
            tap(TASK_POPUP_FLOAT_X[0], TASK_POPUP_FLOAT_X[1], "关任务浮层")
            time.sleep(2)
            items = screen()
            continue

        # 「去首页点击东东农场」限时任务弹窗：X 没有文字，只能固定坐标
        if find(items, "去领取") and find(items, "今日24点前完成", "先到先得"):
            tap(TASK_POPUP_X[0], TASK_POPUP_X[1], "关限时任务弹窗")
            time.sleep(2)
            items = screen()
            continue

        if find(items, "里查看") and find(items, "订阅", "攻略"):
            tap(GUIDE_X[0], GUIDE_X[1], "关引导气泡")
            time.sleep(2)
            items = screen()
            continue

        if not (is_farm(items) or is_task_panel(items)):
            hit = find(items, "关闭", "跳过", "我知道了", "以后再说")
            if hit:
                tap(hit[0], hit[1], "关弹窗:" + hit[2])
                time.sleep(2)
                items = screen()
                continue
        break
    return items


# ---------------- 导航 ----------------

def open_farm():
    log("[1/4] 进入东东农场")
    if not base.ensure_jd():
        log("  [X] 拉不起京东")
        return False

    items = dismiss(screen())
    if is_farm(items):
        log("  已经在农场")
        return True

    for attempt in range(2):
        # URL 里带 ? ，交给设备 shell 时要自己加引号
        base.adb_run(["shell", "am", "start", "-a", "android.intent.action.VIEW",
                      "-d", "'" + FARM_URL + "'", "-p", JD], timeout=40)
        for _ in range(5):
            time.sleep(3)
            items = dismiss(screen())
            if is_farm(items):
                log("  已进入农场")
                return True
        log("  第 %d 次没进去，重试" % (attempt + 1))
        back(1, 2.2)

    log("  [X] 进不去农场")
    return False


def ensure_farm():
    """浏览任务可能跳到商品页 / 验证错误页，用返回键退回农场"""
    for _ in range(4):
        items = dismiss(screen())
        if is_farm(items):
            return items
        back(1, 2.2)
    if open_farm():
        return dismiss(screen())
    return None


def open_task_panel(tries=3):
    for _ in range(tries):
        items = dismiss(screen())
        if is_task_panel(items):
            return items
        if not is_farm(items):
            items = ensure_farm()
            if not items:
                return None
        # 底部「领水滴」入口；OCR 有时也会认出左侧气泡，取最靠下的那个
        hit = find_bottom(items, "领水滴") or tap_pos(TASK_ENTRY)
        tap(hit[0], hit[1], "领水滴")
        for _ in range(3):
            time.sleep(3)
            items = dismiss(screen())
            if is_task_panel(items):
                return items
    log("  任务面板打不开")
    return None


def find_bottom(items, keyword):
    hits = []
    for it in items:
        if keyword not in it[0]:
            continue
        pos = base._char_pos(it, keyword) if it[3] == "L" else (it[1], it[2], keyword)
        if pos:
            hits.append(pos)
    return max(hits, key=lambda p: p[1]) if hits else None


def tap_pos(pos):
    return pos


# ---------------- 签到 ----------------

def do_sign():
    log("[2/4] 每日签到")
    items = dismiss(screen())
    if not is_farm(items):
        return False
    tap(SIGN_ENTRY[0], SIGN_ENTRY[1], "签到")
    time.sleep(4)
    # 签到后常跳「签到得好礼」商品页或弹奖励，退回来即可
    ensure_farm()
    dismiss(screen())
    log("  签到完成")
    return True


# ---------------- 任务面板 ----------------

def parse_rows(items):
    """解析任务面板每一行 → [(按钮y, 按钮x, 按钮文字, 任务标题, 描述)]

    描述很关键：只做「浏览6秒」类任务。其它「完成任务 / 完成访问」类
    会跳外部 App、直播间或系统设置，页面很难自己回来。
    """
    buttons = []
    for kw in PANEL_BTNS:
        for it in items:
            if kw not in it[0]:
                continue
            pos = base._char_pos(it, kw) if it[3] == "L" else (it[1], it[2], kw)
            if pos and pos[0] > 800:          # 只认右侧按钮列
                buttons.append((pos[1], pos[0], kw))
    buttons.sort()

    rows = []
    last_y = -999
    for by, bx, kw in buttons:
        if by - last_y < 35:                 # 同一行去重
            continue
        last_y = by
        titles, descs = [], []
        for it in items:
            if it[3] != "L" or it[1] > 750:
                continue
            x, y, text = it[1], it[2], it[0]
            if by - 130 < y < by + 8 and len(text) > 4:
                titles.append((by - y, text))
            if by + 8 < y < by + 110:
                descs.append(text)
        titles.sort()
        rows.append((by, bx, kw,
                     titles[0][1] if titles else "", " ".join(descs)))
    return rows


def claim_all(items):
    """把面板里所有「去领奖 / 领奖励」点掉；返回领了几个"""
    n = 0
    for _ in range(8):
        hit = None
        for kw in CLAIM_BTNS:
            for it in items:
                if kw not in it[0]:
                    continue
                pos = base._char_pos(it, kw) if it[3] == "L" \
                    else (it[1], it[2], kw)
                if pos and pos[0] > 800:
                    hit = pos
                    break
            if hit:
                break
        if not hit:
            break
        tap(hit[0], hit[1], hit[2])
        n += 1
        time.sleep(2)
        items = dismiss(screen())
    return n, items


def do_tasks():
    log("[3/4] 做领水滴任务")
    items = open_task_panel()
    if not items:
        log("  跳过任务环节")
        return 0

    done = 0
    failed = {}
    for _ in range(MAX_BROWSE + 4):
        if done >= MAX_BROWSE:
            log("  已达单次浏览上限 %d" % MAX_BROWSE)
            break

        devlink.keep_awake(base.adb_run, log)    # 中途掉线/灭屏就地救一次
        # 面板刚打开时 OCR 可能抓到过渡画面，多确认一次再判定
        items = dismiss(screen())
        for __ in range(2):
            if is_task_panel(items):
                break
            time.sleep(2)
            items = dismiss(screen())
        if not is_task_panel(items):
            items = open_task_panel(tries=2)
            if not items:
                break

        n, items = claim_all(items)
        if n:
            log("  领奖 %d 个" % n)
            continue

        def pick(rows):
            """只挑「浏览6秒」类任务，且同一位置最多试 2 次"""
            for by, bx, kw, title, desc in rows:
                if kw in ("去浇水", "去领取") or kw in CLAIM_BTNS:
                    continue
                if any(w in title for w in SKIP_WORDS):
                    continue
                if "浏览" not in desc:       # 关键：非浏览类一律不碰
                    continue
                key = (bx // 40, by // 40)
                if failed.get(key, 0) >= 2:
                    continue
                return (by, bx, title, key)
            return None

        target = pick(parse_rows(items))
        if not target:
            time.sleep(2)                    # 再给面板一点渲染时间
            items = dismiss(screen())
            target = pick(parse_rows(items))
        if not target:
            # 列表下面可能还有任务，最多往下翻 3 屏
            for _ in range(3):
                base.swipe()
                items = dismiss(screen())
                target = pick(parse_rows(items))
                if target:
                    break
        if not target:
            log("  没有可做的浏览任务了")
            break

        by, bx, title, key = target
        tap(bx, by, "去完成:" + title[:12])
        time.sleep(9)                        # 浏览 6 秒即可，多留 3 秒给页面加载
        back(1, 2.5)
        items = ensure_farm()
        if not items:
            break
        done += 1
        log("  完成第 %d 项浏览 (%s)" % (done, title[:12]))

        # 回到面板，若按钮还在原位说明没完成
        items = open_task_panel(tries=2)
        if not items:
            break
        still = any(abs(by - y) < 40 for y, _, _, _, _ in parse_rows(items))
        if still:
            failed[key] = failed.get(key, 0) + 1
        else:
            failed[key] = 0

    # 收尾：把攒下的奖都领了，再关面板准备浇水
    items = open_task_panel(tries=2)
    if items:
        n, items = claim_all(items)
        if n:
            log("  收尾领奖 %d 个" % n)
        tap(PANEL_CLOSE_X[0], PANEL_CLOSE_X[1], "关任务面板")
        time.sleep(2)

    log("  共完成 %d 项浏览" % done)
    return done


# ---------------- 浇水 ----------------

def do_water():
    log("[4/4] 浇水")
    rounds = 0
    stalled = 0                              # 水滴连续不下降 = 被弹窗挡住或浇不动了
    for _ in range(MAX_WATER_ROUND):
        devlink.keep_awake(base.adb_run, log)    # 中途掉线/灭屏就地救一次
        items = dismiss(screen())
        if not is_farm(items):
            items = ensure_farm()
            if not items:
                break
        if is_task_panel(items):
            tap(PANEL_CLOSE_X[0], PANEL_CLOSE_X[1], "关任务面板")
            time.sleep(2)
            items = dismiss(screen())

        before = read_water(items)
        if before is not None:
            log("  当前水滴 %dg" % before)
            if before < 50:                  # 一次「浇5次」要 50g
                log("  水滴不足，停止浇水")
                break

        tap(WATER_POT[0], WATER_POT[1], "浇5次")
        rounds += 1
        time.sleep(3)
        after_items = dismiss(screen())      # 可能弹「升级福利 / 中奖红包」
        after = read_water(after_items)
        if before is not None and after is not None and after >= before:
            stalled += 1
            log("  水滴没减少（可能弹窗挡住），第 %d 次" % stalled)
            if stalled >= 2:
                log("  连续浇不动，停止")
                break
        else:
            stalled = 0
        time.sleep(1)

    log("  浇了 %d 轮（%d 次）" % (rounds, rounds * 5))
    return rounds


# ---------------- 主流程 ----------------

def main():
    log("=" * 46)
    # 设备掉线自动重启 adb 服务，灭屏自动唤醒（见 devlink.py）
    if not devlink.prepare(base.adb_run, log):
        return 2

    if not open_farm():
        shot("fail_nav")
        return 3
    shot("farm_home")

    do_sign()

    if not NO_TASK:
        try:
            do_tasks()
        except Exception as e:
            log("  任务环节异常: %s" % e)

    do_water()

    # 浇完水「每日累计浇水20次」可能已达成，回面板把奖领掉
    items = open_task_panel(tries=2)
    if items:
        n, _ = claim_all(items)
        if n:
            log("  浇水任务领奖 %d 个" % n)

    shot("final")
    log("结束")
    return 0


def watchdog(minutes=15):
    time.sleep(minutes * 60)
    log("[X] 超过 %d 分钟，强制退出" % minutes)
    os._exit(9)


if __name__ == "__main__":
    threading.Thread(target=watchdog, args=(15,), daemon=True).start()
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as e:
        log("崩溃: %s" % e)
        sys.exit(1)
