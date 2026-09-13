#!/bin/bash
# Archive FINALE du VPS OVH, avant sa résiliation.
#
# Différence avec `backup-vps.sh`, qui tourne chaque nuit : celui-ci écrit dans un
# **dépôt à part, sans rétention**. La sauvegarde nocturne purge tout ce qui dépasse
# trente jours ; une archive « définitive » posée à côté d'elle disparaîtrait donc
# exactement au moment où l'on en aurait besoin. Ce script-ci ne purge rien, jamais.
#
# Pour chaque site Laravel trouvé sous /home/*/<domaine>/ :
#   <bucket>/<AAAA-MM-JJ>/<site>/db.sql.gz.gpg       dump MySQL
#   <bucket>/<AAAA-MM-JJ>/<site>/storage.tar.gz.gpg  storage/app (documents, factures…)
#   <bucket>/<AAAA-MM-JJ>/<site>/public.tar.gz.gpg   avatars et signatures manuscrites
#   <bucket>/<AAAA-MM-JJ>/<site>/env.gpg             le .env — il contient APP_KEY,
#                                                    sans laquelle la base est illisible
#   <bucket>/<AAAA-MM-JJ>/MANIFESTE.txt              taille et empreinte de chaque objet
#
# Tout est chiffré en AES-256 (gpg symétrique) AVANT de quitter le Beelink, en flux :
# rien n'est écrit sur le disque local. La passphrase est celle de la sauvegarde
# nocturne : ~/.config/ghosteo-backup/passphrase, dont une copie DOIT être dans le
# gestionnaire de mots de passe de Guilhem — sans elle l'archive ne vaut rien.
#
# Usage : archive-vps.sh [domaine]     (sans argument : tous les sites)
set -uo pipefail

HOST=vito@51.178.87.41
BUCKET=scw:ghosteo-archive-vps-ovh
PASS=$HOME/.config/ghosteo-backup/passphrase
RCLONE=$HOME/.local/bin/rclone
HELPER=$(dirname "$(readlink -f "$0")")/remote-dump.sh
LOG=$HOME/ghosteo-archive.log
DATE=$(date +%F)
ONLY=${1:-}
MANIFESTE=$(mktemp)

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
enc() { gpg --batch --yes --quiet --symmetric --cipher-algo AES256 --passphrase-file "$PASS" -o -; }

trap 'rm -f "$MANIFESTE"' EXIT

[ -f "$PASS" ] || { log "ERREUR : passphrase absente ($PASS)"; exit 1; }
"$RCLONE" mkdir "$BUCKET" 2>>"$LOG" || true

# Un artefact = ssh (helper sur stdin) → gpg → rclone. Avec pipefail, l'échec de
# n'importe quel maillon fait échouer l'ensemble ; le fichier partiel est alors supprimé.
save() {
    local dir=$1 mode=$2 dest=$3
    if ssh -o BatchMode=yes -o ConnectTimeout=15 "$HOST" bash -s -- "$dir" "$mode" < "$HELPER" \
        | enc | "$RCLONE" rcat -q --s3-no-check-bucket "$BUCKET/$dest"; then
        local size hash
        size=$("$RCLONE" size --json "$BUCKET/$dest" 2>/dev/null | sed -E 's/.*"bytes":([0-9]+).*/\1/')
        # L'empreinte est relue DEPUIS le stockage objet, pas calculée ici : elle atteste
        # de ce qui est réellement arrivé à destination, pas de ce qu'on croit avoir envoyé.
        hash=$("$RCLONE" md5sum "$BUCKET/$dest" 2>/dev/null | awk '{print $1}')
        printf '%-52s %12s octets  md5=%s\n' "$dest" "${size:-?}" "${hash:-?}" >> "$MANIFESTE"
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

log "== ARCHIVE FINALE : ${#SITES[@]} sites vers $BUCKET/$DATE"
failed=()
for dir in "${SITES[@]}"; do
    site=$(basename "$dir")
    [ -n "$ONLY" ] && [ "$site" != "$ONLY" ] && continue
    log "-- $site"
    ok=1
    save "$dir" db      "$DATE/$site/db.sql.gz.gpg"      || ok=0
    save "$dir" storage "$DATE/$site/storage.tar.gz.gpg" || ok=0
    save "$dir" public  "$DATE/$site/public.tar.gz.gpg"  || ok=0
    save "$dir" env     "$DATE/$site/env.gpg"            || ok=0
    [ $ok -eq 1 ] || failed+=("$site")
done

# Un passage partiel (archive-vps.sh <domaine>) ne réécrit PAS le manifeste : il ne
# contiendrait que ce seul site et effacerait la trace de tous les autres.
if [ -n "$ONLY" ]; then
    [ ${#failed[@]} -gt 0 ] && { log "== TERMINÉ AVEC ERREURS : ${failed[*]}"; exit 1; }
    log "== Terminé ($ONLY) — manifeste inchangé, le relancer en entier pour le régénérer"
    exit 0
fi

{
    echo "Archive finale du VPS OVH vps-fdce4053 (51.178.87.41), $DATE"
    echo "Chiffrement : gpg symétrique AES-256, passphrase du gestionnaire de mots de passe."
    echo "Restauration d'un artefact :"
    echo "  rclone cat $BUCKET/$DATE/<site>/db.sql.gz.gpg | gpg -d | gunzip > base.sql"
    echo
    sort "$MANIFESTE"
} | "$RCLONE" rcat -q --s3-no-check-bucket "$BUCKET/$DATE/MANIFESTE.txt"

if [ ${#failed[@]} -gt 0 ]; then
    log "== TERMINÉ AVEC ERREURS : ${failed[*]}"
    exit 1
fi
log "== Archive finale terminée sans erreur — AUCUNE rétention sur ce dépôt"
