#!/usr/bin/env bash
set -uo pipefail

cli=/home/savpavi/.local/bin/proton-drive
vault=/home/savpavi/Documents/Obsidian/Aktif\ Kasa
ege=/home/savpavi/Desktop/Ege
stage_root=/home/savpavi/.cache/proton-drive-upload
stage_vault="$stage_root/Obsidian-Aktif-Kasa"
stage_archive="$stage_root/Obsidian-Aktif-Kasa.tar.zst"
stage_ege="$stage_root/Ege"
remote_parent='/my-files/Fedora Yedekleri'
status=/home/savpavi/vm-setup/proton-backup-status.txt

mkdir -p "$stage_vault"
rsync -a --delete \
    --chmod=D755,F644 \
    --exclude='/.codex/' \
    --exclude='/.claude/' \
    --exclude='/.agents/' \
    --exclude='/.mcp.json' \
    --exclude='/tg_session.session' \
    --exclude='/Obsidian/' \
    --exclude='/.trash/' \
    --exclude='/*.sync-conflict-*' \
    "$vault/" "$stage_vault/"

# Proton CLI can misclassify executable plain-text notes as
# application/x-dosexec. Normalize permissions only in the upload staging copy,
# both while copying and once more before upload.
find "$stage_vault" -type d -exec chmod 0755 {} +
find "$stage_vault" -type f -exec chmod 0644 {} +

tar --zstd -cf "$stage_archive.tmp" -C "$stage_root" Obsidian-Aktif-Kasa
mv -f "$stage_archive.tmp" "$stage_archive"

mkdir -p "$stage_ege"
rsync -a --delete --chmod=D755,F644 "$ege/" "$stage_ege/"
find "$stage_ege" -type d -exec chmod 0755 {} +
find "$stage_ege" -type f -exec chmod 0644 {} +

if "$cli" filesystem upload -f replace -t "$stage_archive" "$remote_parent" \
    && "$cli" filesystem upload -d merge -f replace -t "$stage_ege" "$remote_parent"; then
    printf 'SUCCESS %(%F %T %z)T\n' -1 >"$status"
    notify-send -u normal -i folder-cloud 'Proton Drive yedeği tamamlandı' 'Obsidian kasası ve Ege klasörü başarıyla yüklendi.'
else
    result=$?
    printf 'FAILED exit=%s %(%F %T %z)T\n' "$result" -1 >"$status"
    notify-send -u critical -i dialog-error 'Proton Drive yedekleme hatası' "Yükleme tamamlanamadı. Durum: $status"
    exit "$result"
fi
