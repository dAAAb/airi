#!/bin/zsh
set -euo pipefail
# Fixed release and embedded checksums. This script accepts no URLs or filenames.
prefix=@@PREFIX@@
app_name=@@APP@@
release_url=@@URL@@
part_names=(@@NAMES@@)
part_hashes=(@@HASHES@@)
part_sizes=(@@SIZES@@)
archive_bytes=@@TOTAL@@
unpacked_bytes=@@UNPACKED@@
margin_bytes=@@MARGIN@@
installer_dir="${0:A:h}"
parts_dir="$installer_dir/$prefix-parts"

fail() {
  print -u2 -- "停止：$1"
  exit 1
}
checksum_matches() {
  local actual
  actual=$(/usr/bin/shasum -a 256 "$1")
  [[ "${actual%% *}" == "$2" ]]
}
file_size() {
  /usr/bin/stat -f %z "$1"
}

[[ $# == 0 ]] || fail '不接受額外參數。請直接雙擊執行。'
[[ ! -L "$parts_dir" ]] || fail '分片資料夾不能是符號連結。'
/bin/mkdir -p "$parts_dir"
print -- "下載與解壓位置：$installer_dir"
print -- "分片將保留在：$parts_dir"
print -- "安裝包分片總計 $archive_bytes bytes；App 解壓後 $unpacked_bytes bytes。"

remaining_bytes=$archive_bytes
for (( i=1; i<=${#part_names}; i++ )); do
  target="$parts_dir/${part_names[$i]}"
  partial="$target.partial"
  [[ ! -L "$target" && ! -L "$partial" ]] || fail '分片不能是符號連結。'
  if [[ -e "$target" ]]; then
    [[ -f "$target" ]] || fail "不是一般檔案：$target"
    [[ $(file_size "$target") == ${part_sizes[$i]} ]] && checksum_matches "$target" "${part_hashes[$i]}" || fail "已有分片損壞，請檢查後移走再重試：$target"
    remaining_bytes=$(( remaining_bytes - part_sizes[$i] ))
    print -- "已驗證，保留：${part_names[$i]}"
  elif [[ -e "$partial" ]]; then
    [[ -f "$partial" ]] || fail "不是一般檔案：$partial"
    partial_bytes=$(file_size "$partial")
    (( partial_bytes <= part_sizes[$i] )) || fail "續傳檔案過大，請檢查後移走再重試：$partial"
    remaining_bytes=$(( remaining_bytes - partial_bytes ))
    if (( partial_bytes == part_sizes[$i] )); then
      checksum_matches "$partial" "${part_hashes[$i]}" || fail "已下載的續傳檔 SHA256 不符，請檢查後移走再重試：$partial"
      /bin/mv "$partial" "$target"
    fi
  fi
done
required_bytes=$(( remaining_bytes + unpacked_bytes + margin_bytes ))
free_kib=$(/bin/df -Pk "$installer_dir" | /usr/bin/awk 'END {print $4}')
[[ "$free_kib" == <-> ]] || fail '無法讀取可用磁碟空間。'
print -- "目前還需至少 $required_bytes bytes 可用空間（下載餘量＋解壓 App＋2 GiB 餘裕）。"
(( free_kib >= (required_bytes + 1023) / 1024 )) || fail '磁碟空間不足。請把整個安裝器資料夾搬到空間足夠的磁碟。'

for (( i=1; i<=${#part_names}; i++ )); do
  target="$parts_dir/${part_names[$i]}"
  partial="$target.partial"
  if [[ ! -f "$target" ]]; then
    print -- "下載 $i / ${#part_names}：${part_names[$i]}"
    /usr/bin/curl -q --fail --location --proto '=https' --proto-redir '=https' \
      --connect-timeout 30 --speed-limit 1024 --speed-time 90 \
      --retry 5 --retry-all-errors --retry-delay 2 --continue-at - --progress-bar \
      --output "$partial" "$release_url/${part_names[$i]}" || fail "下載中斷，可再執行續傳：$partial"
    [[ $(file_size "$partial") == ${part_sizes[$i]} ]] && checksum_matches "$partial" "${part_hashes[$i]}" || fail "SHA256 或大小不符，不會解壓。請檢查後移走損壞檔再重試：$partial"
    /bin/mv "$partial" "$target"
  fi
done

# Reverify every part before passing any archive bytes to tar.
verified_parts=()
for (( i=1; i<=${#part_names}; i++ )); do
  target="$parts_dir/${part_names[$i]}"
  [[ ! -L "$target" && -f "$target" ]] || fail '分片已被替換。'
  [[ $(file_size "$target") == ${part_sizes[$i]} ]] && checksum_matches "$target" "${part_hashes[$i]}" || fail '分片驗證失敗，不會解壓。'
  verified_parts+=("$target")
done
unpack_dir=$(/usr/bin/mktemp -d "$installer_dir/AIRI-unpacked.XXXXXX")
print -- "驗證通過，解壓到：$unpack_dir"
/bin/cat "${verified_parts[@]}" | /usr/bin/tar -xzf - -C "$unpack_dir"
[[ -d "$unpack_dir/$app_name" && ! -L "$unpack_dir/$app_name" ]] || fail '解壓結果缺少預期 App。'
/usr/bin/codesign --verify --deep --strict "$unpack_dir/$app_name"
print -- '完成。分片已保留；可把 App 移到 Applications。'
/usr/bin/open "$unpack_dir"
