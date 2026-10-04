#!/usr/bin/env bash
# Obsidian "Aktif Kasa" vault'unu git ile yedekler.
# Hedefler (remote 'backup' iki push URL'ine sahip):
#   - /srv/lexar/Backups/obsidian-aktif-kasa.git   (yerel bare)
#   - github.com/savpavi/obsidian-aktif-kasa       (private)
set -uo pipefail

# Ana dalin uzak gecmisini degistirmeden mevcut kasayi surumle.
backup_branch=backup/fedora-host-20260911
exec 9>$HOME/.cache/vault-git-backup.lock
flock -n 9 || exit 0

vault="${VAULT_DIR:-$HOME/Documents/Obsidian/Aktif Kasa}"
status="${STATUS_FILE:-$HOME/vm-setup/vault-git-backup-status.txt}"

note() {  # bildirim varsa gonder, yoksa sessizce gec (systemd icinde DBus olmayabilir)
    command -v notify-send >/dev/null 2>&1 || return 0
    notify-send "$@" >/dev/null 2>&1 || true
}

fail() {  # $1 = stage etiketi (readiness parser'i stage=<slug> bekler), $2 = insan mesaji
    printf 'FAILED exit=1 stage=%s %(%F %T %z)T\n' "$1" -1 >"$status"
    note -u critical -i dialog-error 'Vault yedekleme hatasi' "$2 - detay: $status"
    exit 1
}

cd "$vault" || fail vault-dizini "vault dizinine girilemedi"

git add -A || fail git-add "git add basarisiz"

count=$(git diff --cached --name-only | wc -l)
if ! git diff --cached --quiet; then
    git commit -q -m "Otomatik yedek $(date '+%F %T')" || fail commit "commit basarisiz"
fi
# Degisiklik olmasa da onceki basarisiz push yeniden denenir.
git push -q backup "HEAD:refs/heads/$backup_branch" || fail push "push basarisiz (yerel bare veya GitHub erisilemedi)"

printf 'SUCCESS stage=pushed %(%F %T %z)T\n' -1 >"$status"
note -u low -i folder-cloud 'Vault yedegi tamamlandi' "$count dosya islendi."
