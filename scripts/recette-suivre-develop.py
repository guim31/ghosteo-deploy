#!/usr/bin/env python3
"""Met la recette à jour dès qu'une nouvelle image `:develop` est publiée.

Le circuit voulu par Guilhem : une fusion dans `develop` → une image → la recette suit,
pour qu'il puisse essayer avant de lancer une mise à jour des instances depuis le
back-office. Les deux premiers maillons sont dans GitHub (`docker.yml` construit
`ghcr.io/guim31/ghosteo:develop` à chaque fusion) ; celui-ci est le troisième.

**Pourquoi un guetteur et pas un simple redéploiement périodique.** Le tag `:develop` est
mouvant : son nom ne change pas quand son contenu change. Or `docker compose up -d` ne
retire pas une image qu'il a déjà en cache — Dokploy ne la tire qu'à la première
utilisation. Redéployer sans avoir tiré l'image ne ferait donc rigoureusement rien. Ce
script tire d'abord, compare l'empreinte, et ne redéploie que si elle a bougé.

**Pourquoi depuis le Beelink.** Il détient déjà le jeton de l'API Dokploy et fait tourner
les autres tâches du projet. L'alternative — un secret GitHub et une adresse de
déclenchement — ferait vivre un jeton de déploiement de plus, sur un service de plus.

**Pourquoi control-01 tire et pas le Beelink.** Seul le conteneur Dokploy détient les
identifiants du registre privé ; l'hôte n'en a aucun (`docker pull` y répond
`unauthorized`). On lui délègue donc le tirage, par sa socket partagée.

Usage :
  recette-suivre-develop.py            vérifie, et met à jour si besoin
  recette-suivre-develop.py --forcer   redéploie même sans changement d'image
"""
import argparse
import os
import subprocess
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
from dokploy import call as dokploy          # noqa: E402

CONTROL = "control-01"
IMAGE = "ghcr.io/guim31/ghosteo:develop"
COMPOSE_ID = "jeA57LQPy2ASqs0EXNDV1"          # service « staging » du projet ghosteo
CONTENEUR = "ghosteo-staging-oygder-web-1"
JOURNAL = os.path.expanduser("~/ghosteo-recette.log")
VERROU = "/tmp/.recette-suivre-develop.lock"


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
        log(f"ERREUR sur {CONTROL} : {p.stderr.strip()[:300]}")
        sys.exit(1)
    return p.stdout.strip()


def empreinte():
    return sh(f"docker inspect {IMAGE} --format '{{{{.Id}}}}' 2>/dev/null || true", tolerant=True)


def main():
    a = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--forcer", action="store_true",
                   help="redéployer même si l'image n'a pas changé")
    a = a.parse_args()

    # Deux exécutions simultanées redéploieraient la recette deux fois de suite.
    try:
        verrou = os.open(VERROU, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        age = time.time() - os.path.getmtime(VERROU)
        if age < 1800:
            return
        os.unlink(VERROU)          # verrou abandonné par une exécution morte
        verrou = os.open(VERROU, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        avant = empreinte()
        # Le tirage passe par le conteneur Dokploy, seul détenteur des identifiants.
        # Une panne réseau n'est pas une erreur : on réessaiera au prochain passage.
        tirage = sh("""set -uo pipefail
D=$(docker ps -q -f name=dokploy.1 | head -1)
[ -n "$D" ] || { echo "PANNEAU ABSENT"; exit 0; }
docker exec "$D" docker pull """ + IMAGE + """ >/dev/null 2>&1 && echo TIRE || echo INJOIGNABLE
""", tolerant=True)
        if tirage != "TIRE":
            log(f"image non tirée ({tirage or 'sans réponse'}) — nouvel essai au prochain passage")
            return

        apres = empreinte()
        if avant == apres and not a.forcer:
            return                                  # rien de neuf, on se tait
        if avant == apres:
            log("aucune nouvelle image, redéploiement forcé à la demande")
        else:
            log(f"nouvelle image :develop ({(apres or '?')[7:19]}), la recette va la prendre")

        # L'identifiant du conteneur AVANT : il change à la recréation. Sans lui, la
        # vérification ci-dessous se contenterait de l'état d'avant le redéploiement et
        # annoncerait une réussite sans que rien n'ait bougé — constaté au premier essai.
        conteneur_avant = sh(f"docker inspect {CONTENEUR} --format '{{{{.Id}}}}' 2>/dev/null || true",
                             tolerant=True)

        st, _ = dokploy("POST", "compose.redeploy",
                        {"composeId": COMPOSE_ID, "title": "Recette : nouvelle image develop"})
        if st != 200:
            log(f"ERREUR : redéploiement refusé par le panneau (HTTP {st})")
            return

        # Le conteneur ne doit être recréé que si l'image a réellement changé : à image
        # identique, « docker compose up -d » ne fait rien, et c'est le bon comportement.
        # Exiger la recréation dans ce cas ferait attendre dix minutes pour rien.
        recreation_attendue = avant != apres
        for _ in range(60):
            etat = sh(f"docker inspect {CONTENEUR} "
                      f"--format '{{{{.Id}}}} {{{{.Image}}}} {{{{.State.Health.Status}}}}' "
                      f"2>/dev/null || true", tolerant=True).split()
            if (len(etat) == 3 and etat[1] == apres and etat[2] == "healthy"
                    and (etat[0] != conteneur_avant or not recreation_attendue)):
                log("recette recréée, saine, sur la dernière image de develop" if recreation_attendue
                    else "recette saine ; image inchangée, rien n'avait à être recréé")
                # Chaque image de develop remplacée reste sur le disque, sans étiquette : treize
                # s'étaient accumulées sur control-01 au 23/09/2026. La recette étant saine sur
                # la nouvelle, les anciennes ne servent plus à rien.
                if recreation_attendue:
                    sh("docker image prune -f >/dev/null 2>&1", tolerant=True)
                return
            time.sleep(10)
        log("ATTENTION : la recette n'est pas revenue saine sur la nouvelle image en 10 minutes")
    finally:
        os.close(verrou)
        os.unlink(VERROU)


if __name__ == "__main__":
    main()
