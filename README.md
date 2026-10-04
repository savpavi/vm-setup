# vm-setup

GPU passthrough and Looking Glass configuration for a Windows 11 VM on a Fedora 44 host, plus a few host scripts. These are the files from my running machine, kept so the setup can be rebuilt after a reinstall.

**Hardware:** NVIDIA RTX 5060 passed through to the guest (PCI IDs `10de:2d05` video, `10de:22eb` audio, at `07:00.0/.1`); the host desktop runs on an AMD Radeon RX 9070 XT. Change the IDs and PCI addresses for your card (`lspci -nn`).

## Layout

| Path | Install to | Purpose |
|---|---|---|
| `etc/modprobe.d/vfio.conf` | `/etc/modprobe.d/` | Bind the card to `vfio-pci` before `nouveau`/`nvidia` |
| `etc/dracut.conf.d/vfio.conf` | `/etc/dracut.conf.d/` | Load the VFIO drivers in the initramfs |
| `etc/modprobe.d/kvmfr.conf` | `/etc/modprobe.d/` | 128 MB shared memory for Looking Glass |
| `etc/modules-load.d/kvmfr.conf` | `/etc/modules-load.d/` | Load `kvmfr` at boot |
| `etc/udev/rules.d/99-kvmfr.rules` | `/etc/udev/rules.d/` | `/dev/kvmfr0` ownership (set `YOUR_USER`) |
| `selinux/lookingglass_kvmfr.te` | SELinux module | Lets `svirt_t` use `/dev/kvmfr0` under enforcing SELinux |
| `libvirt/qemu.conf.snippet` | `/etc/libvirt/qemu.conf` | Adds `/dev/kvmfr0` to `cgroup_device_acl` |
| `libvirt/rtx5060-*.xml` | VM definition | `hostdev` entries for the two PCI functions |
| `looking-glass/lg-b7-wayland-scroll-accumulate.patch` | Looking Glass B7 source | Fixes mouse-wheel direction in the native Wayland client |
| `scripts/` | anywhere on `PATH` | Host helpers (below) |

Kernel command line:

```
iommu=pt rd.driver.pre=vfio-pci vfio-pci.ids=10de:2d05,10de:22eb
```

## Install outline

```bash
sudo cp etc/modprobe.d/*.conf /etc/modprobe.d/
sudo cp etc/dracut.conf.d/vfio.conf /etc/dracut.conf.d/
sudo cp etc/modules-load.d/kvmfr.conf /etc/modules-load.d/
sudo cp etc/udev/rules.d/99-kvmfr.rules /etc/udev/rules.d/   # edit YOUR_USER first
sudo grubby --update-kernel=ALL --args="iommu=pt rd.driver.pre=vfio-pci vfio-pci.ids=10de:2d05,10de:22eb"
sudo dracut -f

# SELinux module
checkmodule -M -m -o lookingglass_kvmfr.mod selinux/lookingglass_kvmfr.te
semodule_package -o lookingglass_kvmfr.pp -m lookingglass_kvmfr.mod
sudo semodule -i lookingglass_kvmfr.pp
```

Then merge `libvirt/qemu.conf.snippet` into `/etc/libvirt/qemu.conf`, add the `hostdev` XML to the VM with `virsh edit`, and reboot. After boot, `lspci -k -s 07:00.0` should report `vfio-pci` as the driver.

## Scripts

- `start-windows-looking-glass` starts or resumes the VM (`LG_VM_NAME`, default `win11`) and opens the Looking Glass client; it reuses an existing client window and picks the X11 or native Wayland path per desktop.
- `serve-to-vm.sh` serves a folder to the guest over the libvirt NAT network (`http://192.168.122.1:8000/`), handy for moving installers into Windows.
- `vault-git-backup.sh` commits an Obsidian vault and pushes it to a backup remote from a systemd timer, writing a status file and a desktop notification on failure.

## License

MIT, see `LICENSE`.
