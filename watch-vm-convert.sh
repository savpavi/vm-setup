#!/usr/bin/env bash
set -u

pid_file=/var/lib/libvirt/images/windows-p2v/convert.pid
image_file=/var/lib/libvirt/images/windows-p2v/EGE.qcow2
status_file=/home/savpavi/vm-setup/vm-convert-status.txt

if [[ -r "$pid_file" ]]; then
    convert_pid=$(<"$pid_file")
    while kill -0 "$convert_pid" 2>/dev/null; do
        sleep 20
    done
fi

if qemu-img check "$image_file" >"$status_file" 2>&1; then
    notify-send -u normal -i drive-harddisk "Windows VM hazır" "Disk dönüşümü tamamlandı ve QCOW2 doğrulaması başarılı."
else
    notify-send -u critical -i dialog-error "Windows VM dönüşüm hatası" "QCOW2 doğrulanamadı. Ayrıntı: $status_file"
fi
