# -*- coding: utf-8 -*-
"""ADB 设备自愈（淘宝 / 京东 / 农场三个脚本共用）

定时任务在早上无人值守时跑，最常见的两种失败：

  1) 手机掉线或 adb 服务挂了 —— adb devices 里干脆没有设备
     处理：停服务（adb kill-server）→ 起服务（adb start-server）→ 等重连
     等同于 QtScrcpy 面板上那两个「停止服务 / 启动服务」按钮

  2) 手机还在但已经灭屏 —— 截图全黑，OCR 一个字都认不出来，
     脚本会以为"页面不对"，直接退出
     处理：KEYCODE_WAKEUP + dismiss-keyguard，并回读 mWakefulness 确认真的亮了

调用方各自传入自己的 adb 封装（run(args) -> 文本）和 log 函数，日志格式保持原样。
"""

import time

TIMEOUT_FAST = 25
TIMEOUT_SERVER = 45

# keep_awake 的上次检查时间（秒级缓存，避免每轮都 dumpsys）
_LAST_CHECK = [0.0]


# ---------------- 基础 ----------------

def parse_devices(text):
    """adb devices 输出 → [(serial, state)]；daemon 启动提示行会被跳过"""
    devs = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            devs.append((parts[0], parts[1]))
    return devs


def screen_awake(run):
    """屏幕是否亮着；读不到状态返回 None"""
    txt = run(["shell", "dumpsys", "power"])
    for line in (txt or "").splitlines():
        if "mWakefulness=" in line:
            return "Awake" in line
    txt = run(["shell", "dumpsys", "display"])
    if "mScreenState=ON" in (txt or ""):
        return True
    if "mScreenState=OFF" in (txt or ""):
        return False
    return None


def restart_server(run, log):
    """停服务 → 起服务，让 adb 重新枚举设备"""
    log("  adb 停服务")
    run(["kill-server"])
    time.sleep(2)
    log("  adb 起服务")
    run(["start-server"])
    time.sleep(5)


def wait_device(run, log, rounds=3, wait=8):
    """等设备上线；掉线就重启 adb 服务再来。返回 serial，失败返回空串"""
    for i in range(rounds):
        devs = parse_devices(run(["devices"]))
        good = [s for s, st in devs if st == "device"]
        if good:
            if i:
                log("  设备已恢复: %s" % good[0])
            return good[0]

        if devs:
            log("  设备状态异常: %s" % ", ".join("%s=%s" % d for d in devs))
        else:
            log("  没检测到设备")
        if i == rounds - 1:
            break

        restart_server(run, log)
        t0 = time.time()
        while time.time() - t0 < wait:
            if any(st == "device" for _, st in parse_devices(run(["devices"]))):
                break
            time.sleep(2)

    return ""


def wake(run, log, tries=3):
    """唤醒并解锁屏幕；返回 True 表示确认亮屏"""
    woke = False
    for i in range(tries):
        if screen_awake(run):
            break
        log("  屏幕没亮，唤醒（第 %d 次）" % (i + 1))
        run(["shell", "input", "keyevent", "KEYCODE_WAKEUP"])
        time.sleep(1.5)
        run(["shell", "wm", "dismiss-keyguard"])
        time.sleep(1.5)
        woke = True

    # 亮着也可能是锁屏，解一次（锁屏机型上 dismiss-keyguard 不一定生效，补 MENU 键兜底）
    run(["shell", "wm", "dismiss-keyguard"])
    time.sleep(0.8)
    if woke:
        run(["shell", "input", "keyevent", "KEYCODE_MENU"])
        time.sleep(0.8)

    if screen_awake(run) is False:
        log("  [X] 屏幕仍然不亮（检查数据线、手机是否关机、是否需要重新授权 USB 调试）")
        return False
    return True


def prepare(run, log):
    """启动前固定动作：等设备 → 亮屏解锁。返回 serial，空串表示放弃"""
    log("[0/4] 连接手机")
    serial = wait_device(run, log)
    if not serial:
        log("  [X] 没有设备连接（已尝试重启 adb 服务）")
        return ""
    log("  设备: %s" % serial)
    wake(run, log)
    return serial


def keep_awake(run, log, every=90):
    """长流程中定期确认还连着、还亮着；出问题就地救一次"""
    now = time.time()
    if now - _LAST_CHECK[0] < every:
        return True
    _LAST_CHECK[0] = now

    if not parse_devices(run(["devices"])):
        log("  设备掉线，重启 adb 服务")
        if not wait_device(run, log, rounds=2, wait=6):
            return False
        wake(run, log)
        return True

    if screen_awake(run) is False:
        log("  中途灭屏，唤醒")
        wake(run, log, tries=2)
    return True
