#!/usr/bin/env bash
# Restore a transportable Firebird 2.5 backup as a new Firebird 5 database.
set -euo pipefail
umask 077

usage() {
    cat <<'EOF'
Usage: migrate-firebird-2.5-to-5.sh SOURCE.FDB DESTINATION.FDB

Migrates a local, offline database copy. Never overwrites either argument.
On macOS, downloads and extracts official Firebird 2.5.9 tools temporarily;
it does not install them or replace the system Firebird framework.

Environment:
  ISC_USER          Database user (default: SYSDBA)
  ISC_PASSWORD      Database password (prompted if running interactively)
  FB25_ROOT         Existing 2.5 installation; required outside macOS.
                    On macOS: path to Versions/A inside a Classic framework.
  FB5_BIN           Firebird 5 bin directory (auto-detected on macOS)
  FB5_LIBRARY_PATH  Native library directory (auto-detected on macOS)

The same credentials are used for backup, restore and validation. Stop writers
before running: the source is copied as a file, not backed up through a server.
EOF
}

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
if [[ ${1:-} == --help || ${1:-} == -h ]]; then usage; exit 0; fi
[[ $# == 2 ]] || { usage >&2; exit 2; }
[[ -f $1 ]] || die "Source is not a regular file: $1"
source_dir=$(cd -- "$(dirname -- "$1")" && pwd -P)
source_db="$source_dir/$(basename -- "$1")"
destination_dir=$(cd -- "$(dirname -- "$2")" && pwd -P)
destination_db="$destination_dir/$(basename -- "$2")"
[[ ! -e $destination_db && ! -L $destination_db ]] ||
    die "Destination already exists: $destination_db"

export ISC_USER=${ISC_USER:-SYSDBA}
if [[ -z ${ISC_PASSWORD:-} ]]; then
    [[ -t 0 ]] || die 'Set ISC_PASSWORD before running noninteractively.'
    read -r -s -p 'Firebird password: ' ISC_PASSWORD
    printf '\n' >&2
fi
[[ -n $ISC_PASSWORD ]] || die 'Password must not be empty.'
export ISC_PASSWORD

platform=$(uname -s)
if [[ $platform == Darwin ]]; then
    framework=/Library/Frameworks/Firebird.framework/Versions/A
    FB5_BIN=${FB5_BIN:-$framework/Resources/bin}
    FB5_LIBRARY_PATH=${FB5_LIBRARY_PATH:-$framework/Resources/lib}
fi
[[ -n ${FB5_BIN:-} ]] || die 'Set FB5_BIN to the Firebird 5 bin directory.'
for tool in gbak gfix gstat; do
    [[ -x $FB5_BIN/$tool ]] || die "Missing executable: $FB5_BIN/$tool"
done

work=$(mktemp -d "$destination_dir/.tmp_fb-migration.XXXXXX")
cleanup() { rm -rf -- "$work"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir "$work/locks25" "$work/locks5"

# Keep loader and lock settings isolated between the two engine versions.
run5() (
    unset FIREBIRD FIREBIRD_MSG DYLD_LIBRARY_PATH LD_LIBRARY_PATH
    export FIREBIRD_LOCK="$work/locks5"
    if [[ -n ${FB5_LIBRARY_PATH:-} ]]; then
        export DYLD_LIBRARY_PATH="$FB5_LIBRARY_PATH"
        export LD_LIBRARY_PATH="$FB5_LIBRARY_PATH"
    fi
    "$@"
)
version=$(run5 "$FB5_BIN/gbak" -z 2>&1 || true)
[[ $version == *'Firebird 5.'* ]] || die 'FB5_BIN does not contain Firebird 5.'

if [[ -z ${FB25_ROOT:-} ]]; then
    [[ $platform == Darwin ]] || die 'Set FB25_ROOT to a Firebird 2.5 installation.'
    printf 'Downloading official Firebird 2.5.9 tools...\n'
    curl --fail --location --silent --show-error --max-time 120 \
        'https://github.com/FirebirdSQL/firebird/releases/download/R2_5_9/FirebirdCS-2.5.9-27139-x86_64.pkg' \
        -o "$work/firebird25.pkg"
    pkgutil --expand-full "$work/firebird25.pkg" "$work/firebird25"
    FB25_ROOT="$work/firebird25/FirebirdCS.pkg/Payload/Versions/A"
    resources="$FB25_ROOT/Resources"
    # The installer normally supplies these framework resource links.
    for entry in "$resources/English.lproj/var/"*; do
        [[ -e $resources/$(basename -- "$entry") ]] ||
            ln -s "$entry" "$resources/$(basename -- "$entry")"
    done
fi
FB25_ROOT=$(cd -- "$FB25_ROOT" && pwd -P)
if [[ $platform == Darwin ]]; then
    gbak25="$FB25_ROOT/Resources/bin/gbak"
else
    gbak25="$FB25_ROOT/bin/gbak"
fi
[[ -x $gbak25 ]] || die "Missing executable: $gbak25"
run25() (
    unset FIREBIRD FIREBIRD_MSG DYLD_LIBRARY_PATH LD_LIBRARY_PATH
    export FIREBIRD_LOCK="$work/locks25"
    if [[ $platform == Darwin ]]; then
        export FIREBIRD="$FB25_ROOT/Resources"
        export FIREBIRD_MSG="$FIREBIRD"
        export DYLD_LIBRARY_PATH="$FB25_ROOT:$FB25_ROOT/Libraries"
    else
        export FIREBIRD="$FB25_ROOT"
        export LD_LIBRARY_PATH="$FB25_ROOT/lib"
    fi
    "$@"
)
version=$(run25 "$gbak25" -z 2>&1 || true)
[[ $version == *V2.5.* ]] || {
    printf '%s\n' "$version" >&2
    die 'FB25_ROOT does not contain Firebird 2.5.'
}

checksum() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d ' ' -f 1
    else
        sha256sum "$1" | cut -d ' ' -f 1
    fi
}
original_hash=$(checksum "$source_db")
cp -- "$source_db" "$work/source.fdb"
chmod u+w "$work/source.fdb"
[[ $(checksum "$work/source.fdb") == "$original_hash" ]] ||
    die 'Source changed while copying; stop its writers and retry.'

printf 'Backing up temporary source copy with Firebird 2.5...\n'
backup_status=0
run25 "$gbak25" -backup_database -garbage_collect -verbose \
    "$work/source.fdb" "$work/database.fbk" >"$work/backup.log" 2>&1 ||
    backup_status=$?
if [[ $backup_status != 0 ]]; then
    # The Intel 2.5 macOS tool can abort during shutdown under Rosetta after
    # finishing the backup. Accept only that specific exit and completion marker;
    # restore and full validation below are still required before publication.
    if [[ $platform == Darwin && $backup_status == 134 ]] &&
        ! grep -q 'gbak: ERROR:' "$work/backup.log" &&
        grep -Eq 'closing file, committing, and finishing\..*bytes written' \
            "$work/backup.log" && [[ -s $work/database.fbk ]]; then
        printf 'Warning: legacy tool aborted after completing backup; validating restore.\n' >&2
    else
        cat "$work/backup.log" >&2
        die "Firebird 2.5 backup failed (exit $backup_status)."
    fi
fi

printf 'Restoring and validating with Firebird 5...\n'
if ! run5 "$FB5_BIN/gbak" -create_database "$work/database.fbk" \
    "$work/restored.fdb" >"$work/restore.log" 2>&1; then
    cat "$work/restore.log" >&2
    die 'Firebird 5 restore failed.'
fi
if ! run5 "$FB5_BIN/gfix" -validate -full -no_update "$work/restored.fdb" \
    >"$work/validation.log" 2>&1; then
    cat "$work/validation.log" >&2
    die 'Restored database failed full validation.'
fi
[[ ! -s $work/validation.log ]] || {
    cat "$work/validation.log" >&2
    die 'Validation reported diagnostics; destination has not been published.'
}
run5 "$FB5_BIN/gstat" -h "$work/restored.fdb" >"$work/header.log" 2>&1
grep -Eq 'ODS version[[:space:]]+13\.1([[:space:]]|$)' "$work/header.log" ||
    die 'Restored database does not have Firebird 5 ODS 13.1.'
[[ $(checksum "$source_db") == "$original_hash" ]] ||
    die 'Source changed during migration; destination has not been published.'

# A hard link publishes on the same filesystem and fails if the name exists,
# including if another process creates the destination during migration.
chmod 600 "$work/restored.fdb"
ln -- "$work/restored.fdb" "$destination_db"
printf 'Created: %s\nODS: 13.1; full validation passed; source SHA-256 unchanged.\n' \
    "$destination_db"
