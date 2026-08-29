# cachyos-restore

fedora-host düzenini (Hyprland + VFIO/Windows VM + Looking Glass + arşiv diskleri) CachyOS'ta yeniden kurar.
Yedek: `/srv/storage/Backups/pre-cachy-20260829/` (29 Ağustos 2026; `README.md` içinde içerik listesi).

## Kullanım

```bash
# CachyOS kurulup ilk giriş yapıldıktan sonra (paru hazır gelir):
sudo pacman -S --needed git
git clone https://github.com/savpavi/vm-setup.git ~/vm-setup
cd ~/vm-setup/cachyos-restore
./restore.sh --list          # fazlar
DRY=1 ./restore.sh srv       # önce kuru çalıştır
./restore.sh srv             # /srv diskleri + yedek erişilir olsun
./restore.sh base hypr dotfiles home services   # masaüstü
./restore.sh vm libvirt      # passthrough + VM
./restore.sh flatpak
```

Her fazdan önce sorar; `YES=1` ile sormadan geçer.

## Faz sırası ve ne yapar

| Faz | İş |
|---|---|
| `srv` | Fedora fstab'ındaki `/srv/disk12`, `/srv/disk6`, `/srv/disk1`, `/srv/lexar` (UUID) + mergerfs `/srv/storage` satırlarını ekler, mount eder. Yedek buradan okunur — **ilk bu**. |
| `base` | Temel araçlar (pacman + AUR: 1password, helium, brave, vivaldi, ayugram). Oyun paketleri isteğe bağlı. |
| `hypr` | Hyprland yığını (sdegler COPR'ın Arch karşılıkları), KDE uygulamaları, niri. |
| `dotfiles` | `~/dotfiles` clone + `dot-link` + üç elle symlink + `dot-theme reapply`; `~/vm-setup` clone. |
| `home` | Yedekten seçili klasörler (mod 1) veya her şey (mod 2). Vault'u yedekten değil git/Syncthing'den al. |
| `services` | tailscaled, syncthing@savpavi, libvirt; kullanıcı timer'ları (vault-git-backup, archive-critical-backup, copyparty). |
| `vm` | qemu/libvirt/looking-glass paketleri, `vfio.conf` + `kvmfr` modprobe/udev, mkinitcpio MODULES'a vfio öne, `mkinitcpio -P`. Kernel cmdline'ı önyükleyiciye göre **elle** (limine / sd-boot / grub — script yazdırır). |
| `libvirt` | VM XML'ini Arch edk2 yollarına çevirir (`/usr/share/edk2/x64/*.4m.fd`, qcow2→raw pflash), disk yolunu **`/srv/lexar/VM/`** olarak çevirir, define/net komutlarını yazdırır. VM diski kalıcı olarak Lexar'da (29.08.2026'da taşındı); nvram yedekten elle. |
| `flatpak` | Fedora'daki uygulama listesi (runtime'lar hariç) `--user` olarak. |
| `pkgs` | Yalnız referans: Fedora `dnf-userinstalled.txt` nerede, eşlenmemiş paket nasıl aranır; zsh'i varsayılan kabuk yapar. |

## Bilinen farklar (Fedora → CachyOS)

- `rd.driver.pre=vfio-pci` (dracut) → mkinitcpio `MODULES=(vfio_pci vfio vfio_iommu_type1 ...)` + cmdline `amd_iommu=on iommu=pt`.
- SELinux yok → `lookingglass_kvmfr.pp` gerekmez. kvmfr için `looking-glass-module-dkms` (AUR) + `linux-cachyos-headers`.
- Looking Glass B7 Wayland scroll yaması (`vm-setup/lg-b7-wayland-scroll-accumulate.patch`) AUR paketine uygulanmaz; scroll aşırıysa client'ı yamayla yeniden derle veya master sürümü kullan.
- edk2 firmware Fedora'da qcow2 pflash, Arch'ta raw `.fd`; script XML'i çevirir, nvram'ı `qemu-img convert -O raw` ile taşı.
- GDM → SDDM; oturum `hyprland-uwsm`. DPMS yasağı (amdgpu + aquamarine) muhtemelen CachyOS'ta da geçerli — `hypridle.conf`'ta dpms listener kapalı kalsın, test et.
- Fedora'ya özgü paketler (anaconda, dracut, grub2-*, rpmfusion, abrt, selinux, plasma-setup, livesys) bilerek eşlenmedi.
- Donanım aynı olduğu için PCI adresleri (`07:00.0/1` RTX 5060, `03:00.0` RX 9070 XT) ve disk UUID'leri değişmez; diskleri yeniden bölümlersen `blkid.txt` ile karşılaştır.
