#!/bin/bash
# Sauvegarde nocturne des sites GHosteo du VPS OVH vers Scaleway Object Storage.
#
# Tourne sur le Beelink (cron), qui TIRE les données : le VPS ne détient aucun
# identifiant Scaleway. Pour chaque site Laravel trouvé sous /home/*/<domaine>/ :
#   <site>/<AAAA-MM-JJ>/db.sql.gz.gpg   dump MySQL
#   <site>/<AAAA-MM-JJ>/storage.tar.gz.gpg   storage/app (documents patients, factures…)
#   <site>/<AAAA-MM-JJ>/env.gpg   le .env — il contient APP_KEY, sans laquelle la base est illisible
# Tout est chiffré en AES-256 (gpg symétrique) AVANT de quitter le Beelink, en flux :
# rien n'est écrit sur le disque local. Passphrase : ~/.config/ghosteo-backup/passphrase
# (copie dans le gestionnaire de mots de passe de Guilhem). Rétention : 30 jours.
#
# Usage : backup-vps.sh [domaine]     (sans argument : tous les sites)
set -uo pipefail

HOST=vito@51.178.87.41
BUCKET=scw:ghosteo-backups-vps
PASS=$HOME/.config/ghosteo-backup/passphrase
RCLONE=$HOME/.local/bin/rclone
HELPER=$(dirname "$(readlink -f "$0")")/remote-dump.sh
LOG=$HOME/ghosteo-backup.log
DATE=$(date +%F)
ONLY=${1:-}
RETENTION_DAYS=30

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
enc() { gpg --batch --yes --quiet --symmetric --cipher-algo AES256 --passphrase-file "$PASS" -o -; }
put() { "$RCLONE" rcat -q --s3-no-check-bucket "$BUCKET/$1"; }

# Un artefact = ssh (helper sur stdin) → gpg → rclone. Avec pipefail, l'échec de
# n'importe quel maillon fait échouer l'ensemble ; le fichier partiel est alors supprimé.
save() {
    local dir=$1 mode=$2 dest=$3
    if ssh -o BatchMode=yes -o ConnectTimeout=15 "$HOST" bash -s -- "$dir" "$mode" < "$HELPER" | enc | put "$dest"; then
        local size
        size=$("$RCLONE" size --json "$BUCKET/$dest" 2>/dev/null | sed -E 's/.*"bytes":([0-9]+).*/\1/')
        log "   $mode ok (${size:-?} octets)"
        return 0
    fi
    "$RCLONE" deletefile "$BUCKET/$dest" 2>/dev/null || true
    log "   ERREUR $mode"
    return 1
}

mapfile -t SITES < <(ssh -o BatchMode=yes -o ConnectTimeout=15 "$HOST" \
    'for a in $(find /home -maxdepth 3 -name artisan -not -path "*/vito/*" 2>/dev/null | sort); do d=$(dirname "$a"); [ -f "$d/.env" ] && echo "$d"; done')

if [ ${#SITES[@]} -eq 0 ]; then
    log "ERREUR : aucun site trouvé sur $HOST (SSH en panne ?)"
    exit 1
fi

log "== Début : ${#SITES[@]} sites"
failed=()
for dir in "${SITES[@]}"; do
    site=$(basename "$dir")
    [ -n "$ONLY" ] && [ "$site" != "$ONLY" ] && continue
    log "-- $site"
    ok=1
    save "$dir" db      "$site/$DATE/db.sql.gz.gpg"    || ok=0
    save "$dir" storage "$site/$DATE/storage.tar.gz.gpg" || ok=0
    save "$dir" env     "$site/$DATE/env.gpg"           || ok=0
    [ $ok -eq 1 ] || failed+=("$site")
done

# Rétention : on ne purge que si tout s'est bien passé, pour ne jamais effacer
# une ancienne sauvegarde le jour où la nouvelle a échoué.
if [ ${#failed[@]} -eq 0 ] && [ -z "$ONLY" ]; then
    "$RCLONE" delete --min-age "${RETENTION_DAYS}d" "$BUCKET" 2>>"$LOG" && "$RCLONE" rmdirs --leave-root "$BUCKET" 2>>"$LOG"
    log "== Terminé sans erreur, rétention ${RETENTION_DAYS} j appliquée"
    exit 0
fi

if [ ${#failed[@]} -gt 0 ]; then
    log "== Terminé AVEC ERREURS : ${failed[*]}"
    exit 1
fi
log "== Terminé ($ONLY)"
