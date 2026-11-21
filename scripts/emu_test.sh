#!/bin/bash
# R171: 在 WSL 仿真环境实测 RouterSploit 模块
set -u
cd /opt/FirmAE

# 检查 NR1800X 栈是否已在跑
CODE=$(curl -s -m 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8091/ 2>/dev/null)
echo "NR1800X_8091: $CODE"

if [ "$CODE" != "200" ] && [ "$CODE" != "302" ]; then
  echo "需要重启 NR1800X 栈 (wheezy mipsel)..."
  pkill -9 -f "qemu-system-mipsel.*vm_mips" 2>/dev/null
  sleep 3
  rm -f /tmp/to_console
  pgrep -cf "http.server 8000" >/dev/null || (cd /tmp && setsid nohup python3 -m http.server 8000 > /tmp/h.log 2>&1 &)
  sleep 1
  setsid qemu-system-mipsel -M malta -m 512 \
    -kernel /tmp/vm_mips/vmlinux-mipsel-native \
    -hda /tmp/vm_mips/debian_wheezy_mipsel_standard.qcow2 \
    -append "root=/dev/sda1 rw console=ttyS0" \
    -serial unix:/tmp/to_console,server,nowait -display none \
    -device e1000,netdev=n0 \
    -netdev user,id=n0,hostfwd=tcp::8091-:80 \
    < /dev/null > /tmp/to_qemu.log 2>&1 &
  echo "booting... (waiting 90s for guest)"
  sleep 5
fi
echo "QEMU=$(pgrep -cf 'qemu-system-mipsel.*vm_mips')"
echo EMU_BOOT_DONE
