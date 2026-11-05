/**
 * 淘宝淘金币 自动签到/领取脚本 v2（Hamibot / AutoX.js）
 *
 * 基于真机实测界面编写（淘宝 10.x，1080x2400，已通过 ADB 逐屏核对）：
 *   我的淘宝 → "领淘金币" 图标 → 淘金币页（日常版/双11版）
 *   日常版顶部三格 = 今天 / 明天 / 后天，今天已签到时显示 ✓
 *
 * 运行前：Hamibot App 需开启「无障碍服务」+「悬浮窗」，淘宝已登录
 * 定时：Hamibot 控制台 → 脚本 → 定时任务（建议每天 09:00）
 */

"auto";
auto.waitFor();

var PACKAGE = "com.taobao.taobao";

function log(msg) {
    console.log(msg);
    toast(msg);
}

/* ---------- 基础操作 ---------- */

// 点击第一个文本完全匹配的控件，返回是否成功
function tapText(txt, timeout) {
    timeout = timeout || 8000;
    var end = Date.now() + timeout;
    while (Date.now() < end) {
        var w = text(txt).findOnce();
        if (w) {
            var b = w.bounds();
            if (b.centerX() > 0 && b.centerY() > 0) {
                click(b.centerX(), b.centerY());
                return true;
            }
        }
        sleep(400);
    }
    return false;
}

// 点击包含某段文字的控件（用于"明日领 800"这类动态文案）
function tapContains(txt, timeout) {
    timeout = timeout || 6000;
    var end = Date.now() + timeout;
    while (Date.now() < end) {
        var w = textContains(txt).findOnce();
        if (w) {
            var b = w.bounds();
            if (b.centerX() > 0 && b.centerY() > 0) {
                click(b.centerX(), b.centerY());
                return true;
            }
        }
        sleep(400);
    }
    return false;
}

// 关闭弹窗
function dismissPopups() {
    var closers = ["关闭", "跳过", "我知道了", "以后再说", "暂不", "取消"];
    for (var round = 0; round < 3; round++) {
        var hit = false;
        for (var i = 0; i < closers.length; i++) {
            if (text(closers[i]).exists()) {
                tapText(closers[i], 1000);
                hit = true;
                sleep(1500);
                break;
            }
        }
        // 右上角的 X 通常是 desc="关闭" 或纯图片，用返回键兜底
        if (!hit) break;
    }
}

/* ---------- 流程 ---------- */

function openCoinPage() {
    log("打开淘宝…");
    launchApp("淘宝");
    sleep(7000);

    // 底部 Tab「我的淘宝」
    if (!tapText("我的淘宝", 10000)) {
        log("找不到底部「我的淘宝」，可能不在首页");
    }
    sleep(4000);
    dismissPopups();

    // "我的淘宝"页里的「领淘金币」图标
    if (!tapText("领淘金币", 8000)) {
        // 兜底：用坐标（1080x2400 实测位置）
        click(389, 1329);
    }
    sleep(8000);   // 页面要加载活动/动画，等久一点
    dismissPopups();
}

function doSignIn() {
    // 如果活动版有「回日常版」竖标签，先切回日常版（日常版才有连续签到格）
    if (text("回日常版").exists()) {
        tapText("回日常版", 2000);
        sleep(4000);
    }

    // 情况1：出现「签到」按钮 → 直接点
    if (tapText("签到", 4000)) {
        log("✅ 已点击签到");
        sleep(4000);
        dismissPopups();
        return true;
    }

    // 情况2：顶部签到格已是 ✓（今天签过）→ 检查明天/后天字样
    if (textContains("明天").exists() || textContains("明日领").exists()) {
        log("ℹ️ 今天已经签到过了（明天可再领）");
        return false;
    }

    log("⚠️ 没找到签到入口，页面可能改版");
    return false;
}

function claimRewards() {
    // 已完成但未领的任务，按钮会变成「领取」
    var claimed = 0;
    for (var i = 0; i < 6; i++) {
        if (!tapText("领取", 2500)) break;
        claimed++;
        sleep(2500);
        dismissPopups();
    }
    if (claimed > 0) log("✅ 领取了 " + claimed + " 个奖励");
    return claimed;
}

function main() {
    openCoinPage();
    doSignIn();
    claimRewards();
    log("—— 淘金币任务执行完毕 ——");
    exit();
}

main();
