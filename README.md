# vm-setup

Fedora host üzerinde GPU passthrough'lu Windows VM kurulumu ve yedekleme
scriptlerinin yapılandırma arşivi. Makine yeniden kurulduğunda buradaki
dosyalar referans alınır.

## VFIO / GPU passthrough

| Dosya | Hedef |
|---|---|
| `vfio.conf` | `/etc/modprobe.d/vfio.conf` |
| `vfio-dracut.conf` | `/etc/dracut.conf.d/` |
| `rtx5060-video.xml`, `rtx5060-audio.xml` | libvirt hostdev tanımları |

## Looking Glass

| Dosya | Hedef |
|---|---|
| `kvmfr.conf` | `/etc/modprobe.d/kvmfr.conf` |
| `kvmfr-modules-load.conf` | `/etc/modules-load.d/` |
| `99-kvmfr.rules` | `/etc/udev/rules.d/` |
| `lookingglass_kvmfr.te/.mod/.pp` | SELinux politika modülü |
| `qemu.conf.looking-glass` | `/etc/libvirt/qemu.conf` referansı |
| `lg-b7-wayland-scroll-accumulate.patch` | Looking Glass B7 Wayland scroll yaması |

SELinux modülünü yüklemek için:

```bash
sudo semodule -i lookingglass_kvmfr.pp
```

## Scriptler

- `vault-git-backup.sh` — Obsidian vault'un git tabanlı yedeği (timer'dan çalışır)
- `proton-backup.sh` — Proton Mail arşiv yedeği (araç 26.08.2026'da kaldırıldı, script referans olarak duruyor)
- `watch-vm-convert.sh` — disk imajı dönüştürme izleyicisi

## proton-to-gmail

Proton → Gmail/Workspace göç araçları. Göç tamamlandı ve kapatıldı; kod
referans olarak duruyor. `.env` ve `state.sqlite3` repo'ya dahil değil —
yeniden çalıştırmak gerekirse `setup-wizard.sh` OAuth akışını baştan kurar.
