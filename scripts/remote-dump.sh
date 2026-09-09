#!/bin/bash
# Exécuté SUR LE VPS, reçu par « ssh vito@vps bash -s -- <répertoire du site> <db|storage|env> ».
# Écrit le résultat sur la sortie standard, rien sur le disque, aucun secret affiché.
set -euo pipefail
dir=$1
mode=$2
cd "$dir"

getenv() {
    grep -E "^$1=" .env | head -1 | cut -d= -f2- \
        | sed -e 's/\r$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}

case "$mode" in
    db)
        port=$(getenv DB_PORT); port=${port:-3306}
        host=$(getenv DB_HOST); host=${host:-127.0.0.1}
        export MYSQL_PWD
        MYSQL_PWD=$(getenv DB_PASSWORD)
        mysqldump --single-transaction --quick --no-tablespaces --routines --triggers \
            -h "$host" -P "$port" -u "$(getenv DB_USERNAME)" "$(getenv DB_DATABASE)" | gzip -6
        ;;
    storage)
        # Documents patients, factures, fichiers publics, hardware_id. Les zips
        # temporaires de l'outil de sauvegarde intégré sont exclus.
        # Certains dossiers de documents sont créés par PHP-FPM sous l'utilisateur isolé
        # du site, illisibles pour vito : on lit en sudo (lecture seule) quand c'est possible.
        if sudo -n true 2>/dev/null; then t="sudo -n tar"; else t=tar; fi
        $t -C storage --exclude='app/backups/temp' --exclude='app/backups/restore_temp' -czf - app
        ;;
    env)
        cat .env
        ;;
    *)
        echo "mode inconnu : $mode" >&2
        exit 2
        ;;
esac
