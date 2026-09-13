#!/bin/bash
# Exécuté SUR control-01 ou worker-01, reçu par
#   « ssh <serveur> bash -s -- <appName> <db|storage|env> <instance|backoffice|dokploy> ».
# Écrit le résultat sur la SORTIE STANDARD, rien sur le disque durable, aucun secret affiché.
#
# Pendant du remote-dump.sh de l'ancien VPS, adapté à l'hébergement en conteneurs.
set -euo pipefail
app=${1:-}      # « - » quand aucun service n'est concerné (voir backup-scaleway.sh)
mode=${2:-}
type=${3:-instance}

# Tout ce qui n'est pas l'artefact part sur la sortie d'erreur : le flux de sortie doit
# rester parfaitement propre, il est chiffré puis envoyé tel quel au stockage objet.
exec 3>&1

case "$type:$mode" in

    instance:db)
        # SQLite en mode WAL : copier le fichier à chaud donnerait une base tronquée.
        # « VACUUM INTO » produit une copie cohérente pendant que l'instance travaille.
        # Le PHP part par un fichier, jamais par une ligne de commande imbriquée.
        cat > /tmp/.bk-$$.php <<'PHP'
<?php
$src = '/var/www/html/storage/app/database.sqlite';
$dst = '/tmp/bk.sqlite';
@unlink($dst);
$p = new PDO('sqlite:' . $src);
$p->exec("VACUUM INTO '" . $dst . "'");
PHP
        trap 'rm -f /tmp/.bk-$$.php; docker exec "${app}-web-1" rm -f /tmp/bk.sqlite /tmp/bk.php >/dev/null 2>&1 || true' EXIT
        docker cp /tmp/.bk-$$.php "${app}-web-1":/tmp/bk.php >/dev/null 2>&1
        docker exec "${app}-web-1" php /tmp/bk.php >/dev/null 2>&1
        docker exec "${app}-web-1" cat /tmp/bk.sqlite | gzip -6 >&3
        ;;

    instance:storage|backoffice:storage)
        # Documents patients, factures, hardware_id, et pour le back-office les deux clés
        # des licences hors-ligne. La base SQLite est exclue : elle a son propre artefact,
        # cohérent, et une copie à chaud ici serait trompeuse.
        V=$(docker volume inspect "${app}_storage" --format '{{.Mountpoint}}')
        tar -C "$V" \
            --exclude='app/database.sqlite' --exclude='app/database.sqlite-wal' \
            --exclude='app/database.sqlite-shm' \
            --exclude='app/backups/temp' --exclude='app/backups/restore_temp' \
            -czf - app >&3
        ;;

    instance:env|backoffice:env)
        # Contient APP_KEY : sans elle les dossiers patients (ou, pour le back-office,
        # les jetons d'API en base) sont définitivement illisibles.
        cat "/etc/dokploy/compose/${app}/code/.env" >&3
        ;;

    backoffice:db)
        # Le mot de passe est lu par le shell DU CONTENEUR dans son propre environnement :
        # il n'apparaît ni en argument ni dans un « ps » de la machine hôte.
        docker exec "${app}-db-1" sh -c \
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump --single-transaction --quick --no-tablespaces --routines --triggers -u root "$MYSQL_DATABASE"' \
            | gzip -6 >&3
        ;;

    dokploy:db)
        # La base du panneau : la carte des services, domaines et serveurs. Sans elle,
        # tout se reconstruit à la main. Avec elle, une réinstallation retrouve le parc.
        P=$(docker ps -q -f name=dokploy-postgres | head -1)
        [ -n "$P" ] || { echo "conteneur dokploy-postgres introuvable" >&2; exit 2; }
        docker exec "$P" sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip -6 >&3
        ;;

    *)
        echo "combinaison inconnue : type=$type mode=$mode" >&2
        exit 2
        ;;
esac
