#!/usr/bin/env bash
# GPU passthrough + Looking Glass + Windows VM restore on Arch Linux.
# Run as the normal user after the base system is installed (qemu, libvirt, dkms, headers present).
#
#   setup-vfio.sh                run the default stages in order
#   setup-vfio.sh host cmdline   run only the named stages
#   setup-vfio.sh --dry-run ...  print what would run, change nothing
#   setup-vfio.sh --list         list stages
#
# Default stages: check pkgs host cmdline libvirt vm client
# After them: REBOOT, then run `setup-vfio.sh verify`.
#
# Every file this script edits gets a .bak-<timestamp> copy first.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
BACKUP="${BACKUP:-/srv/lexar/Fedora-to-arch-backup}"
VM="${VM:-EGE-Windows11}"
GPU_IDS="${GPU_IDS:-10de:2d05,10de:22eb}"   # RTX 5060 video + audio
CMDLINE_ADD="iommu=pt vfio-pci.ids=$GPU_IDS"
TS=$(date +%Y%m%d-%H%M%S)
DEFAULT_STAGES=(check pkgs host cmdline libvirt vm client)
ALL_STAGES=(check pkgs host cmdline libvirt vm client verify)
DRY=0
FAILED=()

say()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m !! %s\033[0m\n' "$*"; }
run()  { if (( DRY )); then printf '  [dry] %s\n' "$*"; else "$@"; fi; }
have() { command -v "$1" >/dev/null 2>&1; }
bak()  { [[ -e $1 ]] && run sudo cp -a "$1" "$1.bak-$TS"; return 0; }
# Write stdin to a root-owned file.
put()  { if (( DRY )); then printf '  [dry] write %s\n' "$1"; cat >/dev/null; else sudo tee "$1" >/dev/null; fi; }

stage_check() {
  [[ $EUID -ne 0 ]] || { warn "run as the normal user, not root"; return 1; }
  [[ -r /etc/arch-release ]] || { warn "this is not Arch Linux"; return 1; }
  run sudo -v || return 1
  local id ok=0
  for id in ${GPU_IDS//,/ }; do
    if lspci -nn 2>/dev/null | grep -qi "\[$id\]"; then echo "found PCI device $id"; else warn "PCI device $id not found"; ok=1; fi
  done
  if compgen -G '/sys/kernel/iommu_groups/*' >/dev/null; then echo "IOMMU groups present"; else warn "no IOMMU groups: enable SVM/IOMMU in the firmware setup"; ok=1; fi
  return $ok
}

stage_pkgs() {
  have paru || { warn "paru is missing (dotfiles install.sh aur stage)"; return 1; }
  # kvmfr is built by dkms, so headers for every installed kernel must be present.
  local k missing=()
  for k in $(pacman -Qq | grep -E '^linux(-lts|-zen|-hardened)?$'); do
    pacman -Qq "$k-headers" >/dev/null 2>&1 || missing+=("$k-headers")
  done
  (( ${#missing[@]} )) && run sudo pacman -S --needed --noconfirm "${missing[@]}"
  run sudo pacman -S --needed --noconfirm qemu-desktop libvirt virt-manager virt-install edk2-ovmf swtpm dnsmasq dkms || return 1
  run paru -S --needed --noconfirm --skipreview looking-glass looking-glass-module-dkms || return 1
}

stage_host() {
  say "modprobe / modules-load / udev"
  put /etc/modprobe.d/vfio.conf <<EOF
options vfio-pci ids=$GPU_IDS
softdep nouveau pre: vfio-pci
softdep nvidia pre: vfio-pci
EOF
  put /etc/modprobe.d/kvmfr.conf <<'EOF'
options kvmfr static_size_mb=128
EOF
  put /etc/modules-load.d/kvmfr.conf <<'EOF'
kvmfr
EOF
  # QEMU runs as libvirt-qemu on Arch (qemu on Fedora); the desktop user reaches the device through the kvm group.
  local owner=libvirt-qemu
  getent passwd "$owner" >/dev/null || { owner=$USER; warn "user libvirt-qemu not found, kvmfr owner set to $USER"; }
  put /etc/udev/rules.d/99-kvmfr.rules <<EOF
SUBSYSTEM=="kvmfr", KERNEL=="kvmfr0", OWNER="$owner", GROUP="kvm", MODE="0660"
EOF
  run sudo usermod -aG kvm,libvirt "$USER"
  run sudo udevadm control --reload

  say "initramfs: load vfio before any GPU driver"
  if [[ -d /etc/mkinitcpio.conf.d ]] || have mkinitcpio; then
    run sudo mkdir -p /etc/mkinitcpio.conf.d
    put /etc/mkinitcpio.conf.d/05-vfio.conf <<'EOF'
MODULES+=(vfio_pci vfio vfio_iommu_type1)
EOF
    if have mkinitcpio; then run sudo mkinitcpio -P || return 1; else warn "mkinitcpio not found, initramfs not rebuilt"; fi
  elif have dracut; then
    put /etc/dracut.conf.d/vfio.conf <<'EOF'
force_drivers+=" vfio_pci vfio vfio_iommu_type1 "
EOF
    run sudo dracut -f --regenerate-all || return 1
  else
    warn "neither mkinitcpio nor dracut found; add vfio_pci vfio vfio_iommu_type1 to the initramfs by hand"; return 1
  fi
}

# True when the parameter key of $2 (e.g. iommu=) is already set in $1; amd_iommu= must not count as iommu=.
has_param() { grep -qE -- "(^|[[:space:]\"])${2%%=*}=" "$1"; }

# Append CMDLINE_ADD words that are missing to the value matched by sed expression $2 in file $1.
add_params() {
  local file=$1 word changed=0
  for word in $CMDLINE_ADD; do
    has_param "$file" "$word" && continue
    changed=1
  done
  (( changed )) || { echo "= $file already has the parameters"; return 0; }
  bak "$file"
  for word in $CMDLINE_ADD; do
    has_param "$file" "$word" || run sudo sed -i -E "$2$word$3" "$file"
  done
  echo "+ $file"
}

stage_cmdline() {
  local done_any=0 f
  # Unified kernel images / kernel-install
  if [[ -f /etc/kernel/cmdline ]]; then
    add_params /etc/kernel/cmdline '1 s|[[:space:]]*$| ' '|'; done_any=1
    have mkinitcpio && run sudo mkinitcpio -P
  fi
  # systemd-boot entries (archinstall default)
  for f in /boot/loader/entries/*.conf /efi/loader/entries/*.conf; do
    [[ -f $f ]] || continue
    grep -q '^options' "$f" || continue
    add_params "$f" '/^options/ s|[[:space:]]*$| ' '|'; done_any=1
  done
  # GRUB
  if [[ -f /etc/default/grub ]] && have grub-mkconfig; then
    add_params /etc/default/grub '/^GRUB_CMDLINE_LINUX_DEFAULT=/ s|"[[:space:]]*$| ' '"|'; done_any=1
    run sudo grub-mkconfig -o /boot/grub/grub.cfg
  fi
  # Limine
  for f in /boot/limine.conf /boot/limine/limine.conf /efi/limine.conf; do
    [[ -f $f ]] || continue
    add_params "$f" '/^[[:space:]]*(cmdline|kernel_cmdline)[:=]/I s|[[:space:]]*$| ' '|'; done_any=1
  done
  (( done_any )) || { warn "no known bootloader config found; add by hand: $CMDLINE_ADD"; return 1; }
  echo "current: $(cat /proc/cmdline)"
}

stage_libvirt() {
  local conf=/etc/libvirt/qemu.conf
  if sudo grep -q '^[^#]*/dev/kvmfr0' "$conf" 2>/dev/null; then
    echo "= qemu.conf already allows /dev/kvmfr0"
  else
    bak "$conf"
    (( DRY )) || grep -v '^#' "$REPO/libvirt/qemu.conf.snippet" | sudo tee -a "$conf" >/dev/null
    echo "+ cgroup_device_acl with /dev/kvmfr0"
  fi
  run sudo systemctl enable --now libvirtd.socket || return 1
  if ! sudo virsh net-info default >/dev/null 2>&1; then
    local net="$BACKUP/vm/net-default.xml"
    [[ -r $net ]] || net=/usr/share/libvirt/networks/default.xml
    run sudo virsh net-define "$net"
  fi
  run sudo virsh net-autostart default
  sudo virsh net-info default 2>/dev/null | grep -q 'Active:.*yes' || run sudo virsh net-start default
}

stage_vm() {
  local R="$BACKUP/root-only" xml="$BACKUP/vm/$VM.inactive.xml"
  [[ -r $xml ]] || { warn "$xml not found (is Lexar mounted?)"; return 1; }
  [[ -d $R/vm-images ]] || { warn "$R/vm-images not found: root-backup.sh was not run before the reinstall"; return 1; }

  say "disk images"
  run sudo mkdir -p /var/lib/libvirt/images
  run sudo rsync -a --sparse --update --info=progress2 --exclude=listing.txt "$R/vm-images/" /var/lib/libvirt/images/ || return 1
  run sudo chown -R root:root /var/lib/libvirt/images

  say "TPM state (needed if the guest uses BitLocker / device encryption)"
  local uuid; uuid=$(grep -oP '(?<=<uuid>)[^<]+' "$xml")
  if [[ -d $R/libvirt-var/swtpm/$uuid ]]; then
    run sudo mkdir -p /var/lib/libvirt/swtpm
    run sudo rsync -a "$R/libvirt-var/swtpm/$uuid" /var/lib/libvirt/swtpm/
    getent passwd tss >/dev/null && run sudo chown -R tss:tss "/var/lib/libvirt/swtpm/$uuid"
  else
    warn "no swtpm state for $uuid in the backup; the guest gets an empty TPM"
  fi

  say "UEFI variables (Fedora qcow2 -> Arch raw)"
  local nv="$R/libvirt-var/qemu/nvram/${VM}_VARS.qcow2" dst="/var/lib/libvirt/qemu/nvram/${VM}_VARS.fd"
  run sudo mkdir -p /var/lib/libvirt/qemu/nvram
  if [[ -e $dst ]]; then echo "= $dst exists, left alone"
  elif [[ -r $nv ]]; then run sudo qemu-img convert -O raw "$nv" "$dst"
  else warn "no saved NVRAM; libvirt creates a fresh one (Windows still boots from the default loader path)"; fi

  say "domain definition"
  local out; out=$(mktemp --suffix=.xml)
  # Arch ships raw OVMF without the enrolled-keys feature: drop the explicit loader/nvram and let libvirt pick.
  python3 - "$xml" "$out" <<'PY' || return 1
import re, sys
s = open(sys.argv[1], encoding="utf-8").read()
s = re.sub(r"\n\s*<loader\b.*?</loader>", "", s, flags=re.S)
s = re.sub(r"\n\s*<nvram\b.*?</nvram>", "", s, flags=re.S)
s = re.sub(r"\n\s*<feature enabled='no' name='enrolled-keys'/>", "", s)
s = re.sub(r"machine='pc-q35-[0-9.]+'", "machine='q35'", s)
open(sys.argv[2], "w", encoding="utf-8").write(s)
PY
  grep -nE "<type |<firmware>|feature enabled|<loader|<nvram" "$out"
  if sudo virsh dominfo "$VM" >/dev/null 2>&1; then
    echo "= domain $VM already defined, left alone (new XML kept at $out)"
  else
    run sudo virsh define "$out" || return 1
  fi
}

stage_client() {
  # The launcher script calls /usr/local/bin/looking-glass-client (the Fedora source build path).
  if [[ ! -e /usr/local/bin/looking-glass-client && -x /usr/bin/looking-glass-client ]]; then
    run sudo ln -s /usr/bin/looking-glass-client /usr/local/bin/looking-glass-client
  fi
  [[ -x $HOME/.local/bin/start-windows-looking-glass ]] || run install -Dm755 "$REPO/scripts/start-windows-looking-glass" "$HOME/.local/bin/start-windows-looking-glass"
  [[ -e $HOME/.config/looking-glass/client.ini ]] || warn "$HOME/.config/looking-glass/client.ini missing (comes back with the home restore)"
  echo "now reboot, then run: $0 verify"
}

stage_verify() {
  local ok=0 dev
  for dev in $(lspci -Dnn | grep -iE "\[(${GPU_IDS//,/|})\]" | awk '{print $1}'); do
    local drv; drv=$(basename "$(readlink -f "/sys/bus/pci/devices/$dev/driver" 2>/dev/null)" 2>/dev/null)
    if [[ $drv == vfio-pci ]]; then echo "ok   $dev -> vfio-pci"; else warn "$dev is bound to '${drv:-nothing}', expected vfio-pci"; ok=1; fi
  done
  if [[ -c /dev/kvmfr0 ]]; then ls -l /dev/kvmfr0; [[ -r /dev/kvmfr0 && -w /dev/kvmfr0 ]] || { warn "/dev/kvmfr0 not accessible to $USER (log out and in for the kvm group)"; ok=1; }
  else warn "/dev/kvmfr0 missing: check 'dkms status' and 'modprobe kvmfr'"; ok=1; fi
  grep -q 'iommu=pt' /proc/cmdline || { warn "iommu=pt not on the kernel command line"; ok=1; }
  sudo virsh dominfo "$VM" >/dev/null 2>&1 && echo "ok   domain $VM defined" || { warn "domain $VM not defined"; ok=1; }
  (( ok == 0 )) && echo "all checks passed; start the VM with start-windows-looking-glass (Super+W)"
  return $ok
}

main() {
  local stages=() a
  for a in "$@"; do
    case "$a" in
      --dry-run|-n) DRY=1 ;;
      --list) printf '%s\n' "${ALL_STAGES[@]}"; exit 0 ;;
      -h|--help) sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
      *) if declare -F "stage_$a" >/dev/null; then stages+=("$a"); else echo "unknown stage: $a" >&2; exit 1; fi ;;
    esac
  done
  (( ${#stages[@]} )) || stages=("${DEFAULT_STAGES[@]}")
  local s
  for s in "${stages[@]}"; do
    say "stage: $s"
    "stage_$s" || { FAILED+=("$s"); warn "stage $s reported problems"; [[ $s == check ]] && (( ! DRY )) && break; }
  done
  if (( ${#FAILED[@]} )); then warn "stages with problems: ${FAILED[*]}"; exit 1; fi
}

main "$@"
