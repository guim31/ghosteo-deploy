#!/bin/bash
# Sauvegarde nocturne du NOUVEL hébergement : les instances de worker-01 et le
# back-office de control-01, vers Scaleway Object Storage.
#
# Pourquoi ce script existe : jusqu'au 13/09/2026, les instances migrées n'avaient
# AUCUNE sauvegarde. `backup-vps.sh` ne connaît que l'ancien VPS, dont les copies sont
# figées depuis les bascules. Éteindre le VPS sans ce script laisserait les dossiers
# patients à un seul endroit, sur une seule machine.
#
# Comme pour l'ancien VPS, c'est le Beelink qui TIRE : les serveurs Scaleway ne
# détiennent aucun identifiant de stockage, et tout est chiffré en AES-256 avant de
# quitter cette machine, en flux, sans rien écrire sur le disque local.
#
#   <bucket>/<site>/<AAAA-MM-JJ>/db.sqlite.gz.gpg    base SQLite, copie cohérente
#   <bucket>/<site>/<AAAA-MM-JJ>/storage.tar.gz.gpg  documents patients, factures
#   <bucket>/<site>/<AAAA-MM-JJ>/env.gpg             le .env, dont APP_KEY
#   <bucket>/ghosteo.eu/<date>/db.sql.gz.gpg         le back-office, en MySQL
#   <bucket>/_dokploy/<date>/db.sql.gz.gpg           la base du panneau Dokploy
#
# Passphrase : ~/.config/ghosteo-backup/passphrase, la même que l'ancien VPS — une copie
# DOIT être dans le gestionnaire de mots de passe de Guilhem. Rétention : 30 jours.
#
# Usage : backup-scaleway.sh [nom]     (sans argument : tout)
set -uo pipefail

BUCKET=scw:ghosteo-backups-scaleway
PASS=$HOME/.config/ghosteo-backup/passphrase
RCLONE=$HOME/.local/bin/rclone
HELPER=$(dirname "$(readlink -f "$0")")/remote-dump-scaleway.sh
LOG=$HOME/ghosteo-backup-scaleway.log
DATE=$(date +%F)
ONLY=${1:-}
RETENTION_DAYS=30
WORKER=worker-01
CONTROL=control-01

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }
enc() { gpg --batch --yes --quiet --symmetric --cipher-algo AES256 --passphrase-file "$PASS" -o -; }

[ -f "$PASS" ] || { log "ERREUR : passphrase absente ($PASS)"; exit 1; }
"$RCLONE" mkdir "$BUCKET" 2>>"$LOG" || true

# Un artefact = ssh (helper sur stdin) → gpg → rclone. Avec pipefail, l'échec de
# n'importe quel maillon fait échouer l'ensemble ; le fichier partiel est alors supprimé.
# Note : « ssh hote bash -s -- "$app" ... » joint ses arguments par des espaces, donc un
# argument VIDE disparaît purement et simplement et décale tous les suivants. C'est ce qui
# a fait échouer la sauvegarde du panneau au premier passage. D'où le tiret pour « pas de
# service concerné », jamais une chaîne vide.
save() {
    local hote=$1 app=$2 mode=$3 type=$4 dest=$5
    if ssh -o BatchMode=yes -o ConnectTimeout=15 "$hote" bash -s -- "$app" "$mode" "$type" < "$HELPER" \
        | enc | "$RCLONE" rcat -q --s3-no-check-bucket "$BUCKET/$dest"; then
        local size
        size=$("$RCLONE" size --json "$BUCKET/$dest" 2>/dev/null | sed -E 's/.*"bytes":([0-9]+).*/\1/')
        # Un artefact vide ou dérisoire est un échec silencieux : mieux vaut le dire.
        if [ "${size:-0}" -lt 200 ]; then
            log "   ATTENTION $mode : ${size:-0} octets, c'est suspect"
        else
            log "   $mode ok (${size} octets)"
        fi
        return 0
    fi
    "$RCLONE" deletefile "$BUCKET/$dest" 2>/dev/null || true
    log "   ERREUR $mode"
    return 1
}

# Les instances sont découvertes, jamais listées en dur : une instance ajoutée demain
# doit être sauvegardée sans que personne n'ait à y penser.
mapfile -t INSTANCES < <(ssh -o BatchMode=yes -o ConnectTimeout=15 "$WORKER" \
    'for d in /etc/dokploy/compose/*/code; do
       [ -f "$d/.env" ] || continue
       url=$(grep -E "^APP_URL=" "$d/.env" | head -1 | cut -d= -f2- | tr -d "\"")
       case "$url" in *ghosteoapp.eu*) ;; *) continue ;; esac
       echo "$(basename $(dirname $d)) ${url#https://}"
     done')

if [ ${#INSTANCES[@]} -eq 0 ]; then
    log "ERREUR : aucune instance trouvée sur $WORKER (SSH en panne ?)"
    exit 1
fi

log "== Début : ${#INSTANCES[@]} instances + back-office + panneau"
failed=()

for ligne in "${INSTANCES[@]}"; do
    app=${ligne%% *}
    site=${ligne##* }
    [ -n "$ONLY" ] && [ "$site" != "$ONLY" ] && continue
    log "-- $site"
    ok=1
    save "$WORKER" "$app" db      instance "$site/$DATE/db.sqlite.gz.gpg"   || ok=0
    save "$WORKER" "$app" storage instance "$site/$DATE/storage.tar.gz.gpg" || ok=0
    save "$WORKER" "$app" env     instance "$site/$DATE/env.gpg"            || ok=0
    [ $ok -eq 1 ] || failed+=("$site")
done

# Le back-office : sa base MySQL, ses fichiers (dont les clés des licences hors-ligne)
# et son .env, dont APP_KEY déchiffre les jetons d'API rangés en base.
BO=$(ssh -o BatchMode=yes -o ConnectTimeout=15 "$CONTROL" \
     'ls /etc/dokploy/compose/ | grep "^ghosteo-backoffice" | head -1')
if [ -n "$BO" ] && { [ -z "$ONLY" ] || [ "$ONLY" = "ghosteo.eu" ]; }; then
    log "-- ghosteo.eu (back-office)"
    ok=1
    save "$CONTROL" "$BO" db      backoffice "ghosteo.eu/$DATE/db.sql.gz.gpg"     || ok=0
    save "$CONTROL" "$BO" storage backoffice "ghosteo.eu/$DATE/storage.tar.gz.gpg" || ok=0
    save "$CONTROL" "$BO" env     backoffice "ghosteo.eu/$DATE/env.gpg"           || ok=0
    [ $ok -eq 1 ] || failed+=("ghosteo.eu")
elif [ -z "$ONLY" ]; then
    log "ERREUR : service du back-office introuvable sur $CONTROL"
    failed+=("ghosteo.eu")
fi

# La base du panneau : sans elle, retrouver quel service porte quel domaine sur quel
# serveur se fait à la main. Elle ne contient pas les dossiers patients.
if [ -z "$ONLY" ] || [ "$ONLY" = "_dokploy" ]; then
    log "-- panneau Dokploy"
    save "$CONTROL" - db dokploy "_dokploy/$DATE/db.sql.gz.gpg" || failed+=("_dokploy")
fi

# Rétention : on ne purge que si tout s'est bien passé, pour ne jamais effacer une
# ancienne sauvegarde le jour où la nouvelle a échoué.
if [ ${#failed[@]} -eq 0 ] && [ -z "$ONLY" ]; then
    "$RCLONE" delete --min-age "${RETENTION_DAYS}d" "$BUCKET" 2>>"$LOG" && \
        "$RCLONE" rmdirs --leave-root "$BUCKET" 2>>"$LOG"
    log "== Terminé sans erreur, rétention ${RETENTION_DAYS} j appliquée"
    exit 0
fi

if [ ${#failed[@]} -gt 0 ]; then
    log "== Terminé AVEC ERREURS : ${failed[*]}"
    exit 1
fi
log "== Terminé ($ONLY)"
