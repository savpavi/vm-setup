#!/usr/bin/env bash
# CachyOS geri yükleme scripti — fedora-host düzenini CachyOS'ta yeniden kurar.
# Kaynak yedek: /srv/storage/Backups/pre-cachy-20260829 (BACKUP ile değiştirilebilir)
#
# Kullanım:
#   ./restore.sh                 # tüm fazları sırayla, her fazdan önce sorar
#   ./restore.sh pkgs hypr       # yalnız seçilen fazlar
#   ./restore.sh --list          # fazları göster
#   DRY=1 ./restore.sh ...       # komutları yazdır, çalıştırma
#
# Fazlar (sıra önemli): base pkgs hypr vm flatpak srv dotfiles home services libvirt
# Root gerektiren adımlar sudo ile çalışır; script normal kullanıcı (savpavi) olarak başlatılır.
set -euo pipefail

BACKUP="${BACKUP:-/srv/storage/Backups/pre-cachy-20260829}"
ME="${SUDO_USER:-$USER}"
HOME_DIR="/home/$ME"
AUR="${AUR:-paru}"   # CachyOS'ta paru hazır gelir; yay da olur

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
run()  { if [[ "${DRY:-0}" == 1 ]]; then printf '  $ %s\n' "$*"; else "$@"; fi; }
sudo_run() { if [[ "${DRY:-0}" == 1 ]]; then printf '  # %s\n' "$*"; else sudo "$@"; fi; }
ask()  { [[ "${YES:-0}" == 1 ]] && return 0; read -r -p "  -> $1 [E/h] " a; [[ -z "$a" || "$a" =~ ^[EeYy] ]]; }
need_backup() { [[ -d "$BACKUP" ]] || { echo "Yedek bulunamadı: $BACKUP — /srv/storage mount edilmiş mi? (srv fazını önce çalıştır)"; exit 1; }; }

# ---------------------------------------------------------------- paket listeleri
# Fedora'daki dnf-userinstalled listesinden elle eşlendi. Fedora'ya özgü olanlar
# (anaconda, dracut, grub2, rpmfusion, selinux, abrt, plasma-setup...) bilerek yok.
PKGS_BASE=(
  base-devel git gh github-cli openssh rsync curl wget2 zip unzip 7zip tar
  vim zsh zsh-autosuggestions zsh-syntax-highlighting fish bash-completion
  starship fzf fd ripgrep eza zoxide yazi btop fastfetch tree lsof psmisc thefuck
  python-pipx uv nodejs npm pandoc-cli
  man-db man-pages words
  btrfs-progs e2fsprogs dosfstools exfatprogs ntfs-3g xfsprogs parted smartmontools nvme-cli efibootmgr
  mergerfs restic syncthing tailscale cloudflared wireguard-tools
  pipewire pipewire-alsa pipewire-pulse wireplumber pavucontrol
  ffmpeg mpv vlc mediainfo mkvtoolnix-cli tesseract tesseract-data-tur
  android-tools scrcpy openrgb liquidctl piper solaar
  libreoffice-fresh
  noto-fonts noto-fonts-cjk noto-fonts-emoji ttf-jetbrains-mono-nerd
  plocate xdg-user-dirs xdg-utils
  flatpak
)
PKGS_BASE_AUR=( 1password 1password-cli helium-browser-bin brave-bin vivaldi ayugram-desktop-bin )

PKGS_HYPR=(
  hyprland hypridle hyprlock hyprpaper hyprpicker hyprpolkitagent hyprcursor uwsm
  xdg-desktop-portal-hyprland xdg-desktop-portal-gtk
  waybar rofi-wayland swaync cliphist wl-clipboard grim slurp satty wf-recorder swayosd
  kitty ghostty alacritty
  brightnessctl playerctl pamixer network-manager-applet blueman
  polkit-kde-agent qt5-wayland qt6-wayland
  dolphin ark gwenview okular spectacle kcalc kate filelight kdeconnect
  gnome-keyring
  niri
)
PKGS_HYPR_AUR=( hyprshot hyprlauncher wlogout matugen-bin waypaper )

PKGS_VM=(
  qemu-full libvirt virt-manager virt-install edk2-ovmf swtpm dnsmasq dmidecode
  dkms linux-cachyos-headers guestfs-tools spice-vdagent
)
PKGS_VM_AUR=( looking-glass looking-glass-module-dkms )

PKGS_GAMES=( steam gamemode gamescope mangohud goverlay wine winetricks qbittorrent )

# ---------------------------------------------------------------- fazlar
phase_base() {
  log "base: pacman paketleri"
  sudo_run pacman -Syu --needed --noconfirm "${PKGS_BASE[@]}"
  log "base: AUR paketleri ($AUR)"
  run "$AUR" -S --needed --noconfirm "${PKGS_BASE_AUR[@]}" || warn "AUR'da bir paket adı değişmiş olabilir; tek tek dene"
  ask "Oyun/wine paketleri de kurulsun mu?" && sudo_run pacman -S --needed --noconfirm "${PKGS_GAMES[@]}"
}

phase_pkgs() {
  log "pkgs: referans listeler (Fedora)"
  echo "  Fedora userinstalled: $BACKUP/sysinfo/dnf-userinstalled.txt"
  echo "  Eşlenmemiş olanlar için: grep -i <ad> $BACKUP/sysinfo/dnf-userinstalled.txt && pacman -Ss <ad>"
  run chsh -s /bin/zsh "$ME" || true
}

phase_hypr() {
  log "hypr: Hyprland yığını"
  sudo_run pacman -S --needed --noconfirm "${PKGS_HYPR[@]}"
  run "$AUR" -S --needed --noconfirm "${PKGS_HYPR_AUR[@]}" || warn "AUR paketlerinden biri kurulamadı"
  warn "Fedora'da GDM kullanılıyordu; CachyOS'ta SDDM/ly gelir. Oturum: hyprland-uwsm.desktop tercih."
}

phase_vm() {
  need_backup
  log "vm: sanallaştırma paketleri"
  sudo_run pacman -S --needed --noconfirm "${PKGS_VM[@]}"
  run "$AUR" -S --needed --noconfirm "${PKGS_VM_AUR[@]}" || warn "looking-glass AUR kurulamadı — B7 + Wayland scroll yaması: $BACKUP/vm/vm-setup-repo/lg-b7-wayland-scroll-accumulate.patch"
  log "vm: VFIO (RTX 5060 = 10de:2d05 + 10de:22eb)"
  sudo_run install -m644 "$BACKUP/vm/vm-setup-repo/vfio.conf" /etc/modprobe.d/vfio.conf
  sudo_run install -m644 "$BACKUP/vm/vm-setup-repo/kvmfr.conf" /etc/modprobe.d/kvmfr.conf
  sudo_run install -m644 "$BACKUP/vm/vm-setup-repo/kvmfr-modules-load.conf" /etc/modules-load.d/kvmfr.conf
  sudo_run install -m644 "$BACKUP/vm/vm-setup-repo/99-kvmfr.rules" /etc/udev/rules.d/99-kvmfr.rules
  # mkinitcpio: vfio modülleri amdgpu'dan ÖNCE yüklenmeli (Fedora'daki rd.driver.pre=vfio-pci karşılığı)
  if ! grep -q vfio_pci /etc/mkinitcpio.conf; then
    sudo_run sed -i 's/^MODULES=(\(.*\))/MODULES=(vfio_pci vfio vfio_iommu_type1 \1)/' /etc/mkinitcpio.conf
  fi
  grep -n '^MODULES' /etc/mkinitcpio.conf 2>/dev/null || true
  # kernel parametreleri — CachyOS'un önyükleyicisine göre elle:
  warn "Kernel cmdline'a ekle: amd_iommu=on iommu=pt  (vfio-pci.ids modprobe.d'den geliyor)"
  warn "  limine : /boot/limine.conf  → cmdline satırı"
  warn "  sd-boot: /etc/sdboot-manage.conf LINUX_OPTIONS → sudo sdboot-manage gen"
  warn "  grub   : /etc/default/grub GRUB_CMDLINE_LINUX_DEFAULT → grub-mkconfig -o /boot/grub/grub.cfg"
  sudo_run mkinitcpio -P
  log "vm: Looking Glass client ve başlatıcı"
  run install -Dm755 "$BACKUP/vm/start-windows-looking-glass" "$HOME_DIR/.local/bin/start-windows-looking-glass"
  warn "looking-glass-client binary'si Fedora derlemesi; Arch'ta AUR paketi kullan (B7 + scroll yaması gerekiyorsa yeniden derle)."
}

phase_flatpak() {
  need_backup
  log "flatpak: flathub + uygulamalar (runtime satırları atlanır)"
  run flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
  local apps
  apps=$(awk -F'\t' '$1 !~ /^org\.(freedesktop|gnome|kde|gtk)\./ {print $1}' "$BACKUP/sysinfo/flatpak.txt" | sort -u)
  # Fedora'da bir kısmı system, bir kısmı user kurulumuydu; burada hepsi --user
  run flatpak install --user -y --noninteractive flathub $apps || warn "bazı flatpak'ler kurulamadı"
}

phase_srv() {
  log "srv: arşiv diskleri + Lexar + mergerfs havuzu (UUID'ler Fedora fstab'ından)"
  sudo_run mkdir -p /srv/disk12 /srv/disk6 /srv/disk1 /srv/lexar /srv/storage
  local src="$BACKUP/sysinfo/fstab"
  [[ -f "$src" ]] || src="$(dirname "$0")/fstab.srv"
  if ! grep -q '/srv/storage' /etc/fstab; then
    if [[ "${DRY:-0}" == 1 ]]; then echo "  # fstab'a eklenecek satırlar:"; grep -E '^(UUID=[^ ]+ /srv/|/srv/disk12:)' "$src" | sed 's/^/  #   /'
    else grep -E '^(UUID=[^ ]+ /srv/|/srv/disk12:)' "$src" | sudo tee -a /etc/fstab >/dev/null; fi
  fi
  sudo_run systemctl daemon-reload
  sudo_run mount -a || warn "mount -a hata verdi; blkid ile UUID'leri karşılaştır ($BACKUP/sysinfo/blkid.txt)"
  df -h /srv/lexar /srv/storage 2>/dev/null || true
}

phase_dotfiles() {
  log "dotfiles: ~/dotfiles + symlink'ler"
  if [[ ! -d "$HOME_DIR/dotfiles/.git" ]]; then
    run git clone git@github.com:savpavi/dotfiles.git "$HOME_DIR/dotfiles" || run git clone https://github.com/savpavi/dotfiles.git "$HOME_DIR/dotfiles"
  fi
  run "$HOME_DIR/dotfiles/bin/dot-link"
  run mkdir -p "$HOME_DIR/.bashrc.d" "$HOME_DIR/Pictures/wallpapers"
  run ln -sfn "$HOME_DIR/dotfiles/docs/hyprland-cheatsheet.md" "$HOME_DIR/hyprland-cheatsheet.md"
  run ln -sfn "$HOME_DIR/dotfiles/themes" "$HOME_DIR/Pictures/wallpapers/omarchy"
  run ln -sfn "$HOME_DIR/dotfiles/shell/50-tools.sh" "$HOME_DIR/.bashrc.d/50-tools.sh"
  grep -q 'dotfiles/bin' "$HOME_DIR/.zshrc" 2>/dev/null || echo 'export PATH="$HOME/dotfiles/bin:$PATH"' >> "$HOME_DIR/.zshrc"
  run "$HOME_DIR/dotfiles/bin/dot-theme" reapply || warn "tema uygulanamadı (hyprland oturumu açık değilse normal)"
  if [[ ! -d "$HOME_DIR/vm-setup/.git" ]]; then
    run git clone https://github.com/savpavi/vm-setup.git "$HOME_DIR/vm-setup"
  fi
}

phase_home() {
  need_backup
  log "home: yedekten geri yükleme ($BACKUP/home → $HOME_DIR)"
  echo "  Mod 1 (önerilen): seçili klasörler — .ssh .gnupg .gitconfig .zshrc .bashrc .bashrc.d .claude .codex .config/{Codex,Claude,gh,syncthing,systemd,1Password,rclone,BraveSoftware,vivaldi,mozilla,obsidian} .local/bin .local/share/{stash,claude} Documents Projects Desktop Downloads Pictures Music Yedekler kok-dosyalari kategorile"
  echo "  Mod 2: her şey (Fedora'ya özgü .config/plasma*, kde*, gnome vs. dahil — önerilmez)"
  local mode; read -r -p "  -> mod [1/2] " mode
  local R=(rsync -aHAX --info=progress2)
  if [[ "$mode" == 2 ]]; then
    run "${R[@]}" "$BACKUP/home/" "$HOME_DIR/"
  else
    local items=(.ssh .gnupg .gitconfig .zshrc .bashrc .bashrc.d .claude .codex .local/bin Documents Projects Desktop Downloads Pictures Music Yedekler kok-dosyalari kategorile
      .config/Codex .config/Claude .config/gh .config/syncthing .config/systemd .config/1Password .config/rclone .config/BraveSoftware .config/vivaldi .config/mozilla .config/obsidian .config/hypr .config/niri
      .local/share/stash .local/share/claude .local/share/AyuGramDesktop)
    for i in "${items[@]}"; do
      [[ -e "$BACKUP/home/$i" ]] || continue
      run mkdir -p "$(dirname "$HOME_DIR/$i")"
      run "${R[@]}" "$BACKUP/home/$i" "$HOME_DIR/$(dirname "$i")/"
    done
  fi
  run chmod 700 "$HOME_DIR/.ssh"; run chmod 600 "$HOME_DIR"/.ssh/id_* 2>/dev/null || true
  warn "Obsidian vault'u yedekten değil Syncthing/git'ten gel: git clone git@github.com:savpavi/obsidian-aktif-kasa.git '$HOME_DIR/Documents/Obsidian/Aktif Kasa'"
  warn "~/.bashrc.d/99-secrets.sh yedekte var ve gizli bilgi içerir; izinlerini kontrol et."
}

phase_services() {
  log "services: sistem"
  sudo_run systemctl enable --now tailscaled
  sudo_run systemctl enable --now "syncthing@$ME"
  sudo_run systemctl enable --now libvirtd.socket virtqemud.socket 2>/dev/null || sudo_run systemctl enable --now libvirtd
  sudo_run usermod -aG libvirt,kvm,input "$ME"
  log "services: kullanıcı timer'ları (unit dosyaları ~/.config/systemd/user'dan geldi)"
  run systemctl --user daemon-reload
  for u in vault-git-backup.timer archive-critical-backup.timer copyparty.service cloudflared-copyparty.service; do
    run systemctl --user enable --now "$u" || warn "$u etkinleştirilemedi"
  done
  warn "tailscale up ile yeniden bağlan; VPS ssh host'u ~/.ssh/config'ten gelir. 1Password SSH agent'ı da yeniden aç."
}

phase_libvirt() {
  need_backup
  log "libvirt: EGE-Windows11 tanımı"
  local x="/tmp/EGE-Windows11.cachyos.xml"
  # Fedora edk2 yolları → Arch edk2-ovmf yolları (qcow2 pflash yerine raw .fd)
  sed -e 's#/usr/share/edk2/ovmf/OVMF_CODE_4M.secboot.qcow2#/usr/share/edk2/x64/OVMF_CODE.secboot.4m.fd#' \
      -e 's#/usr/share/edk2/ovmf/OVMF_VARS_4M.secboot.qcow2#/usr/share/edk2/x64/OVMF_VARS.4m.fd#' \
      -e "s#format='qcow2'\(.*pflash\)#format='raw'\1#" \
      -e "s#templateFormat='qcow2' format='qcow2'#templateFormat='raw' format='raw'#" -e 's#EGE-Windows11_VARS.qcow2#EGE-Windows11_VARS.fd#' \
      -e 's#/var/lib/libvirt/images/windows-p2v/#/srv/lexar/VM/#g' \
      "$BACKUP/vm/EGE-Windows11.inactive.xml" > "$x"
  grep -n -E "loader|nvram" "$x"
  warn "Yukarıdaki loader/nvram yollarının Arch'ta var olduğunu doğrula: ls /usr/share/edk2/x64/"
  warn "Disk imajı kalıcı olarak /srv/lexar/VM/EGE.qcow2 (+ virtio-win.iso) — XML o yola çevrildi; kopyalama gerekmez. Lexar mount olmalı (srv fazı)."
  [[ -f /srv/lexar/VM/EGE.qcow2 ]] && qemu-img check /srv/lexar/VM/EGE.qcow2 | tail -2 || warn "/srv/lexar/VM/EGE.qcow2 bulunamadı!"
  echo "  İzin: sudo chown savpavi:kvm /srv/lexar/VM/*.qcow2 (qemu.conf user=savpavi) ; dizin 755. Sonra:"
  echo "    sudo virsh define $x"
  echo "    sudo virsh net-define $BACKUP/vm/net-default.xml; sudo virsh net-autostart default; sudo virsh net-start default"
  echo "  qemu.conf: user='$ME', cgroup_device_acl'e /dev/kvmfr0 — referans $BACKUP/vm/vm-setup-repo/qemu.conf.looking-glass"
  echo "  nvram: yedekteki EGE-Windows11_VARS.qcow2 → qemu-img convert -O raw ... /var/lib/libvirt/qemu/nvram/EGE-Windows11_VARS.fd (Windows boot girdileri için)"
  echo "  IOMMU grupları referans: $BACKUP/vm/iommu-groups.txt (07:00.0/07:00.1 kendi grubunda olmalı)"
}

# ---------------------------------------------------------------- ana akış
ALL=(base pkgs hypr vm flatpak srv dotfiles home services libvirt)
if [[ "${1:-}" == "--list" ]]; then printf '%s\n' "${ALL[@]}"; exit 0; fi
SEL=("${@:-${ALL[@]}}")
for p in "${SEL[@]}"; do
  declare -f "phase_$p" >/dev/null || { echo "bilinmeyen faz: $p"; exit 1; }
done
for p in "${SEL[@]}"; do
  ask "Faz '$p' çalıştırılsın mı?" && "phase_$p" || warn "faz '$p' atlandı"
done
log "bitti. Yeniden giriş yap (gruplar, zsh), sonra hyprland-uwsm oturumu aç."
