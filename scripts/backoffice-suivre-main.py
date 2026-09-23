#!/usr/bin/env python3
"""Met ghosteo.eu en ligne à chaque fusion dans `main` du back-office.

Avant la migration, Guilhem déployait le back-office d'un clic dans Vito. Depuis, une fusion
dans `main` publie bien une image (`ghcr.io/guim31/ghosteoeu-main:main-<sha>` et `:latest`),
mais rien ne la mettait en ligne : les corrections #65 et #66 du 14/09/2026 attendaient ainsi
sans que personne ne le voie. Ce script referme la boucle, sur le modèle de la recette.

Règle qui en découle, à connaître avant de fusionner quoi que ce soit dans `main` de
`ghosteoeu-main` : **fusionner, c'est mettre en ligne**, dans les cinq minutes. C'était déjà la
convention écrite du dépôt (« sa livraison est la fusion d'une pull request dans `main` ») ;
elle est désormais vraie.

Trois filets, parce que ghosteo.eu est le serveur de licences de tous les cabinets :

1. **Copie de la base avant chaque mise en ligne**, sur control-01, les dix dernières gardées.
   Une migration ne se défait pas en changeant d'image : c'est cette copie qui la défait.
2. **Vérification réelle** : conteneur recréé sur la nouvelle image, sain, et `/up` comme
   `/login` à 200 en visant l'adresse du serveur, jamais par un résolveur.
3. **Retour automatique à l'image précédente** si la vérification échoue en dix minutes. Les
   instances ne voient rien : elles gardent leur licence en cache douze heures. Une image qui
   a échoué n'est plus retentée d'elle-même — sans cela, le cron recommencerait la même
   mise en ligne ratée toutes les cinq minutes.

Usage :
  backoffice-suivre-main.py                     met en ligne la dernière image de main si elle a changé
  backoffice-suivre-main.py --tag main-abc1234  met en ligne cette image précise (retour arrière manuel)
  backoffice-suivre-main.py --etat              image en service, dernière publiée, derniers événements
"""
import argparse
import os
import re
import subprocess
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
from dokploy import call as dokploy          # noqa: E402

CONTROL = "control-01"
IP_CONTROL = "51.158.96.49"
DEPOT = "ghcr.io/guim31/ghosteoeu-main"
APP = "ghosteo-backoffice-w33xq9"
MARQUE = os.path.expanduser("~/.config/dokploy/backoffice.composeId")
ECHEC = os.path.expanduser("~/.config/dokploy/backoffice.echec")
JOURNAL = os.path.expanduser("~/ghosteo-backoffice-deploiement.log")
VERROU = "/tmp/.backoffice-suivre-main.lock"
COPIES = "/root/backoffice-avant-deploiement"      # sur control-01
GARDER = 10


def log(message):
    ligne = f"{time.strftime('%F %T')} {message}"
    print(ligne)
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write(ligne + "\n")


def sh(script, tolerant=False):
    """Script envoyé par l'entrée standard : jamais de guillemets imbriqués."""
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
                        CONTROL, "bash -s"], input=script, capture_output=True, text=True)
    if p.returncode != 0 and not tolerant:
        log(f"ERREUR sur {CONTROL} : {(p.stdout + p.stderr).strip()[:400]}")
        sys.exit(1)
    return p.stdout.strip()


def tirer(ref):
    # Seul le conteneur Dokploy détient les identifiants du registre privé.
    return sh(f"""D=$(docker ps -q -f name=dokploy.1 | head -1)
[ -n "$D" ] || {{ echo PANNEAU-ABSENT; exit 0; }}
docker exec "$D" docker pull {ref} >/dev/null 2>&1 && echo TIRE || echo INJOIGNABLE""", tolerant=True)


def id_image(ref):
    return sh(f"docker inspect {ref} --format '{{{{.Id}}}}' 2>/dev/null || true", tolerant=True)


def version_de(ref):
    return sh(f"docker inspect {ref} --format "
              f"'{{{{index .Config.Labels \"org.opencontainers.image.version\"}}}}' 2>/dev/null || true",
              tolerant=True)


def service():
    cid = open(MARQUE).read().strip()
    st, c = dokploy("GET", "compose.one", query={"composeId": cid})
    if st != 200:
        log(f"ERREUR : le panneau ne décrit pas le service du back-office (HTTP {st})")
        sys.exit(1)
    env = c.get("env") or ""
    m = re.search(r'^GHOSTEO_IMAGE="?([^"\n]+?)"?\s*$', env, re.M)
    return cid, env, (m.group(1) if m else None)


def poser_image(cid, env, ref):
    """Change la seule ligne GHOSTEO_IMAGE ; refuse tout autre changement."""
    neuf = re.sub(r'^GHOSTEO_IMAGE=.*$', f'GHOSTEO_IMAGE="{ref}"', env, count=1, flags=re.M)
    lignes = [1 for a, b in zip(env.split("\n"), neuf.split("\n")) if a != b]
    if len(lignes) != 1 or env.count("APP_KEY") != neuf.count("APP_KEY"):
        log("ERREUR : la modification toucherait autre chose que l'image — rien n'est changé")
        return False
    st, _ = dokploy("POST", "compose.saveEnvironment",
                    {"composeId": cid, "env": neuf, "createEnvFile": True})
    return st == 200


def copier_base(etiquette):
    """Copie de la base avant mise en ligne : c'est elle, et non l'image, qui défait une migration."""
    sortie = sh(f"""set -euo pipefail
mkdir -p {COPIES} && chmod 700 {COPIES}
F={COPIES}/$(date +%Y%m%d-%H%M%S)-avant-{etiquette}.sql.gz
docker exec {APP}-db-1 sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump --single-transaction --quick --no-tablespaces --routines --triggers -u root "$MYSQL_DATABASE"' | gzip -6 > "$F"
chmod 600 "$F"
T=$(stat -c %s "$F")
[ "$T" -gt 100000 ] || {{ echo "copie anormalement petite : $T octets"; exit 1; }}
ls -1t {COPIES}/*.sql.gz | tail -n +{GARDER + 1} | xargs -r rm -f
echo "$F ($T octets)"
""")
    return sortie


def conteneur():
    return sh(f"docker inspect {APP}-web-1 --format '{{{{.Id}}}}' 2>/dev/null || true", tolerant=True)


def attendre(image_id, conteneur_avant):
    """Recréé, sur la bonne image, sain, et qui répond — les quatre, pas un de moins."""
    for _ in range(60):
        etat = sh(f"docker inspect {APP}-web-1 "
                  f"--format '{{{{.Id}}}} {{{{.Image}}}} {{{{.State.Health.Status}}}}' 2>/dev/null || true",
                  tolerant=True).split()
        if len(etat) == 3 and etat[0] != conteneur_avant and etat[1] == image_id and etat[2] == "healthy":
            codes = sh(f"for p in up login; do curl -s -o /dev/null -w '%{{http_code}} ' --max-time 15 "
                       f"--resolve ghosteo.eu:443:{IP_CONTROL} https://ghosteo.eu/$p; done",
                       tolerant=True).split()
            if codes == ["200", "200"]:
                return True
        time.sleep(10)
    return False


def redeployer(cid, titre):
    st, _ = dokploy("POST", "compose.redeploy", {"composeId": cid, "title": titre})
    return st == 200


def menage_images(garder=3):
    """Retire les images du back-office au-delà des `garder` plus récentes, et les couches orphelines.

    Chaque mise en ligne tire une image de 842 Mo et rien ne les retirait : le 23/09/2026,
    control-01 en gardait 28 et son disque était à 87 %. On garde celle en service et les deux
    précédentes — de quoi revenir en arrière sans rien tirer ; au-delà, ghcr les conserve.
    Une image encore utilisée par un conteneur refuse de partir : l'échec est sans conséquence.
    """
    sortie = sh(f"""avant=$(df --output=avail -B1M / | tail -1)
docker images {DEPOT} --format '{{{{.CreatedAt}}}}|{{{{.Repository}}}}:{{{{.Tag}}}}' | grep ':main-' \\
  | sort -r | tail -n +{garder + 1} | cut -d'|' -f2 | xargs -r docker rmi >/dev/null 2>&1
docker image prune -f >/dev/null 2>&1
apres=$(df --output=avail -B1M / | tail -1)
echo "$(( apres - avant )) $(df --output=pcent / | tail -1 | tr -d ' ')"
""", tolerant=True).split()
    if len(sortie) == 2 and int(sortie[0]) > 0:
        log(f"  ménage des images : {int(sortie[0])} Mo libérés, disque à {sortie[1]}")


def mettre_en_ligne(etiquette, force=False):
    cid, env, actuelle = service()
    if not actuelle:
        log("ERREUR : image actuelle du back-office illisible — rien n'est fait")
        return False
    cible = f"{DEPOT}:{etiquette}"
    if actuelle == cible and not force:
        return True
    if tirer(cible) != "TIRE":
        log(f"image {etiquette} non tirée — nouvel essai au prochain passage")
        return False
    nouvel_id = id_image(cible)

    log(f"mise en ligne de {etiquette} (en service : {actuelle.split(':')[-1]})")
    log(f"  copie de la base : {copier_base(etiquette)}")
    avant = conteneur()
    if not poser_image(cid, env, cible):
        return False
    if not redeployer(cid, f"Back-office : {etiquette}"):
        log("ERREUR : redéploiement refusé par le panneau — image précédente reposée")
        _, env2, _ = service()
        poser_image(cid, env2, actuelle)
        return False
    if attendre(nouvel_id, avant):
        log(f"ghosteo.eu en ligne sur {etiquette}, sain, /up et /login à 200")
        if os.path.exists(ECHEC):
            os.unlink(ECHEC)
        menage_images()
        return True

    # Retour arrière. La base n'est pas restaurée d'office : une restauration écraserait ce
    # qui a été saisi entre-temps. La copie est là si la migration doit être défaite.
    log(f"ATTENTION : {etiquette} n'est pas revenue saine en 10 minutes — retour à {actuelle.split(':')[-1]}")
    with open(ECHEC, "w") as f:
        f.write(etiquette)
    tirer(actuelle)
    ancien_id = id_image(actuelle)
    _, env3, _ = service()
    avant = conteneur()
    if poser_image(cid, env3, actuelle) and redeployer(cid, f"Back-office : retour à {actuelle.split(':')[-1]}") \
            and attendre(ancien_id, avant):
        log(f"retour arrière réussi, ghosteo.eu de nouveau sur {actuelle.split(':')[-1]}. "
            f"{etiquette} ne sera plus retentée d'elle-même.")
    else:
        log("ÉCHEC DU RETOUR ARRIÈRE — intervention nécessaire sur control-01")
    return False


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--tag", help="mettre en ligne cette image précise, par exemple main-abc1234")
    a.add_argument("--etat", action="store_true", help="afficher l'état sans rien changer")
    a = a.parse_args()

    if a.etat:
        _, _, actuelle = service()
        tirer(f"{DEPOT}:latest")
        print(f"en service          : {actuelle}")
        print(f"dernière de main    : {DEPOT}:{version_de(DEPOT + ':latest')}")
        print(f"image refusée       : {open(ECHEC).read().strip() if os.path.exists(ECHEC) else 'aucune'}")
        return

    try:
        verrou = os.open(VERROU, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if time.time() - os.path.getmtime(VERROU) < 3600:
            return
        os.unlink(VERROU)
        verrou = os.open(VERROU, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        if a.tag:
            mettre_en_ligne(a.tag, force=True)
            return
        if tirer(f"{DEPOT}:latest") != "TIRE":
            return                                   # réseau : on réessaiera
        derniere = version_de(f"{DEPOT}:latest")
        if not re.fullmatch(r"main-[0-9a-f]{7}", derniere or ""):
            log(f"ERREUR : version illisible sur l'image latest ({derniere!r}) — rien n'est fait")
            return
        if os.path.exists(ECHEC) and open(ECHEC).read().strip() == derniere:
            return                                   # déjà ratée, attend une image plus récente
        mettre_en_ligne(derniere)
    finally:
        os.close(verrou)
        os.unlink(VERROU)


if __name__ == "__main__":
    main()
