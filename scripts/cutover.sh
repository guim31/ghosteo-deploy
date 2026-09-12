#!/bin/bash
# Bascule d'un ou plusieurs cabinets, pensée pour tourner sans surveillance (cron du Beelink).
#
#   cutover.sh guilhem-henry                     un cabinet
#   cutover.sh xavier-pages cedric-rousseau ...   plusieurs, l'un après l'autre
#
# Chaque cabinet doit avoir été préparé (« migrate-instance.py preparer »), ce qui ne coupe
# rien. Cette commande-ci coupe : maintenance, sauvegarde à froid, conversion, contrôle de
# conformité, installation, bascule d'adresse, certificat, vérification, rattachement.
#
# En cas d'échec à n'importe quelle étape, le retour arrière est tenté automatiquement :
# l'adresse retourne à l'ancien serveur et l'ancienne instance sort de maintenance. Un
# cabinet en échec n'empêche pas les suivants.
#
# Journal : ~/ghosteo-bascule.log. Rien n'est affiché sur la sortie standard hors résumé.
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1
LOG="$HOME/ghosteo-bascule.log"
resume=""

# --auto-retrait : la ligne de crontab qui a lancé ce script se supprime après coup.
# Une bascule est un geste unique ; une entrée oubliée rejouerait la migration d'un
# cabinet déjà migré, avec les données du VPS devenues obsolètes.
AUTO_RETRAIT=0
if [ "${1:-}" = "--auto-retrait" ]; then AUTO_RETRAIT=1; shift; fi

for client in "$@"; do
  {
    echo
    echo "================ $(date '+%F %T') bascule de $client"
  } >> "$LOG"
  if python3 -u scripts/migrate-instance.py basculer "$client" >> "$LOG" 2>&1; then
    if python3 -u scripts/migrate-instance.py backoffice "$client" >> "$LOG" 2>&1; then
      echo "$(date '+%F %T') >>> $client MIGRÉ" >> "$LOG"
      resume="$resume$client : migré"$'\n'
    else
      # La bascule a réussi, seul le rattachement au back-office a échoué : le client est
      # en service, on ne revient pas en arrière pour si peu, on le signale.
      echo "$(date '+%F %T') >>> $client migré MAIS rattachement back-office à refaire" >> "$LOG"
      resume="$resume$client : migré, rattachement back-office à refaire à la main"$'\n'
    fi
  else
    echo "$(date '+%F %T') >>> $client ÉCHEC — retour arrière" >> "$LOG"
    if python3 -u scripts/migrate-instance.py retour-arriere "$client" >> "$LOG" 2>&1; then
      resume="$resume$client : ÉCHEC, revenu sur l'ancien serveur"$'\n'
    else
      resume="$resume$client : ÉCHEC ET RETOUR ARRIÈRE EN ÉCHEC — intervention nécessaire"$'\n'
    fi
  fi
done

{
  echo "---------------- $(date '+%F %T') résumé"
  printf '%s' "$resume"
} >> "$LOG"
printf '%s' "$resume"

if [ "$AUTO_RETRAIT" = 1 ]; then
  motif="cutover.sh --auto-retrait $*"
  if crontab -l 2>/dev/null | grep -Fq "$motif"; then
    crontab -l 2>/dev/null | grep -Fv "$motif" | crontab -
    echo "$(date '+%F %T') ligne de crontab retirée : $motif" >> "$LOG"
  fi
fi
