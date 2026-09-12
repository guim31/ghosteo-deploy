#!/bin/bash
# Exécuté SUR LE VPS, reçu par « ssh vito@vps bash -s -- <répertoire> <utilisateur> ».
# Affiche les comptes des tables qui servent à valider une migration. Aucune donnée affichée,
# seulement des nombres. Évite d'imbriquer des guillemets dans une commande ssh.
set -euo pipefail
dir=$1
user=$2
cat > /tmp/.counts-$$.php <<'PHP'
<?php
$tables = ['patients', 'consultations', 'comptabilites', 'users', 'patient_files'];
$out = [];
foreach ($tables as $t) {
    try { $out[] = $t . '=' . \DB::table($t)->count(); }
    catch (\Throwable $e) { $out[] = $t . '=absente'; }
}
echo implode(' ', $out), PHP_EOL;
PHP
chmod 644 /tmp/.counts-$$.php
trap 'rm -f /tmp/.counts-$$.php' EXIT
# tinker sort parfois en code non nul même après avoir affiché son résultat : on ne s'y fie pas,
# c'est la présence de la ligne de comptes qui vaut succès.
ligne=$(sudo -n -u "$user" bash -c "cd '$dir' && php artisan tinker /tmp/.counts-$$.php" 2>/dev/null | grep -E 'patients=' | tail -1 || true)
if [ -z "$ligne" ]; then echo "COMPTAGE IMPOSSIBLE" >&2; exit 1; fi
echo "$ligne"
