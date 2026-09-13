#!/usr/bin/env python3
"""Bascule du back-office GHosteo (ghosteo.eu) du VPS OVH vers control-01.

Le back-office n'est PAS une instance cliente : `migrate-instance.py` ne convient pas
(il suppose SQLite, un volume `storage` et une zone DNS chez Scaleway). C'est le serveur
de licences dont dépendent les huit instances ; elles gardent leur licence en cache
12 heures et fonctionnent sans lui, donc une coupure de quelques minutes est invisible.

Trois différences avec la migration d'un cabinet, à avoir en tête :

1. **La base reste MySQL.** Elle fait 7,7 Mo, le dump se restaure tel quel, et il n'y en
   a qu'une : le choix SQLite servait à multiplier les instances.
2. **La zone `ghosteo.eu` est chez OVH, pas chez Scaleway** (elle porte le courrier).
   Les enregistrements se changent donc À LA MAIN par Guilhem dans son espace client.
   La bascule s'arrête pour l'attendre ; c'est la commande `dns` qui reprend ensuite.
3. **Deux ordonnanceurs ne doivent jamais tourner ensemble.** Le planificateur fait
   avancer les déploiements et sonde les instances chaque minute. Pendant la répétition,
   les conteneurs `scheduler` et `queue` de la copie sont donc arrêtés ; sur le VPS,
   c'est le mode maintenance qui les met en sommeil (Laravel n'exécute ni les tâches
   planifiées ni la file d'attente quand l'application est « down »).

Les commandes, dans l'ordre :

  preparer        répétition à blanc sur control-01 : service, base, données du jour.
                  AUCUNE coupure, rien n'est publié, aucun domaine déclaré.
  basculer        le créneau : maintenance sur le VPS, sauvegarde à froid, restauration,
                  contrôle de conformité. S'ARRÊTE avant le DNS et dicte ce qu'il faut
                  saisir chez OVH.
  dns             une fois les adresses changées : vérifie la propagation, déclare
                  ghosteo.eu et www.ghosteo.eu, obtient le certificat.
  verifier        contrôles finaux, en visant l'adresse et jamais par un résolveur.
  licences        force les huit instances à revalider leur licence et le prouve.
  retour-arriere  remet l'ancien back-office en service et dicte le retour du DNS.

  maintenance / service   mettre l'ANCIEN back-office en maintenance, ou l'en sortir.
"""
import argparse
import json
import os
import subprocess
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
from dokploy import call as dokploy          # noqa: E402

VPS = "vito@51.178.87.41"
IP_VPS = "51.178.87.41"
CONTROL = "control-01"
IP_CONTROL = "51.158.96.49"
WORKER = "worker-01"
DOMAINE = "ghosteo.eu"
DOMAINES = ["ghosteo.eu", "www.ghosteo.eu"]
REPERTOIRE = "/home/ghosteoserver/ghosteo.eu"
UTILISATEUR = "ghosteoserver"
ENV_DOKPLOY = "pC_5KlfCgctYLUpawSQS3"   # projet ghosteo, environnement production
NOM = "backoffice"
TRAVAIL = "/root/migration-backoffice"   # sur control-01
DUMP = os.path.join(ICI, "remote-dump.sh")
COMPOSE = os.path.join(os.path.dirname(ICI), "compose", "backoffice.yml")
MARQUE = os.path.expanduser("~/.config/dokploy/backoffice.composeId")

# Serveurs de noms à interroger : celui qui fait autorité pour la zone (OVH), puis
# trois résolveurs publics, pour voir ce que voit le reste du monde.
NS_AUTORITE = "ns100.ovh.net"
RESOLVEURS = ["8.8.8.8", "1.1.1.1", "9.9.9.9"]

# Variables imposées par l'hébergement en conteneur, quelles que soient celles d'origine.
FORCE = {
    "DB_CONNECTION": "mysql",
    "DB_HOST": "db",            # le service voisin dans le même compose
    "DB_PORT": "3306",
    "DB_DATABASE": "ghosteoserver_db",
    "DB_USERNAME": "ghosteo",
    "LOG_CHANNEL": "stderr",
    "LOG_STACK": "stderr",
    "TRUSTED_PROXIES": "*",
    "APP_URL": "https://ghosteo.eu",
}
# Variables d'un hébergement mutualisé qui n'ont plus de sens ici. DB_PASSWORD en fait
# partie : un mot de passe neuf est tiré pour la base en conteneur.
RETIRER = {
    "DB_PASSWORD", "MEMCACHED_HOST",
    "REDIS_CLIENT", "REDIS_HOST", "REDIS_PASSWORD", "REDIS_PORT",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION",
    "AWS_BUCKET", "AWS_USE_PATH_STYLE_ENDPOINT",
}
# Tables dont le contenu bouge tout seul et qui ne prouvent rien : elles sont restaurées
# comme les autres, simplement exclues de la comparaison.
VOLATILES = {"sessions", "cache", "cache_locks", "jobs", "job_batches", "failed_jobs"}
# Les tables qui portent le métier. Un écart sur l'une d'elles arrête tout, même pendant
# la répétition à blanc. Les autres peuvent bouger d'elles-mêmes tant que la source est
# en service : `instance_checks` grossit de plusieurs lignes toutes les cinq minutes
# (55 734 lignes au 13/09/2026), et l'élagage quotidien en retire.
METIER = {"users", "licenses", "instances", "settings", "plans", "servers",
          "subscriptions", "subscription_items", "email_templates", "site_deployments"}


def sortir(message):
    print("ERREUR :", message, file=sys.stderr)
    sys.exit(1)


def etape(titre):
    print(f"\n\033[1m— {titre}\033[0m")


def sh(cible, commande, entree=None, silencieux=False, tolerant=False):
    """Commande shell sur une machine distante ; sort en erreur si elle échoue."""
    p = subprocess.run(["ssh", "-o", "ConnectTimeout=15", cible, commande],
                       input=entree, capture_output=True, text=True)
    if p.returncode != 0 and not tolerant:
        sortir(f"{cible} : {commande[:70]}…\n{p.stderr[:900]}")
    if not silencieux and p.stdout:
        print(p.stdout.rstrip())
    return p.stdout


def script_distant(cible, script):
    """Envoie un script par l'entrée standard plutôt que dans la ligne de commande.

    Imbriquer des guillemets dans « ssh … bash -c "… --execute='…'" » est ingérable et
    échoue EN SILENCE (la commande est mal découpée, le code de retour reste 0). Trois
    commandes ont déjà été avalées ainsi pendant la phase 5.
    """
    p = subprocess.run(["ssh", "-o", "ConnectTimeout=15", cible, "bash -s"],
                       input=script, capture_output=True, text=True)
    if p.returncode != 0:
        sortir(f"{cible} : script en échec\n{p.stderr[:900]}")
    return p.stdout


# ------------------------------------------------------------------- le service

def compose_id():
    if not os.path.exists(MARQUE):
        sortir(f"{MARQUE} absent — lancer « preparer » d'abord.")
    return open(MARQUE).read().strip()


def app_name():
    cid = compose_id()
    st, p = dokploy("GET", "compose.one", query={"composeId": cid})
    if st != 200:
        sortir(f"compose.one (HTTP {st}) : {p}")
    return cid, p["appName"]


def attendre_sain(minutes=10, app=None):
    app = app or app_name()[1]
    for _ in range(minutes * 6):
        etat = sh(CONTROL, f"docker ps --format '{{{{.Names}}}} {{{{.Status}}}}' | grep {app}-web-1 || true",
                  silencieux=True)
        if "healthy" in etat:
            print(f"  conteneur web sain : {etat.strip()}")
            return
        time.sleep(10)
    sortir("le conteneur web n'est pas devenu sain dans le délai imparti. "
           f"Journal : ssh {CONTROL} docker logs {app}-web-1 --tail 40")


# ------------------------------------------------------------------ maintenance

def maintenance(activer):
    """Met l'ANCIEN back-office en maintenance, ou l'en sort.

    Le mode maintenance de Laravel ne fait pas que renvoyer une page : il met aussi en
    sommeil les tâches planifiées et la file d'attente. C'est ce qui garantit qu'un seul
    ordonnanceur tourne pendant la bascule, et que les comptes de la base ne bougent plus
    entre la sauvegarde et le contrôle de conformité.
    """
    action = "down --retry=120" if activer else "up"
    script = ("set -euo pipefail\n"
              f"sudo -n -u {UTILISATEUR} bash -c 'cd {REPERTOIRE} && php artisan {action}'\n")
    p = subprocess.run(["ssh", "-o", "ConnectTimeout=15", VPS, "bash -s"],
                       input=script, capture_output=True, text=True)
    if p.returncode != 0:
        sortir(f"« php artisan {action} » a échoué sur l'ancien back-office :\n{p.stderr[:500]}")
    print("  ancien back-office " + ("EN MAINTENANCE (planificateur et file en sommeil)"
                                     if activer else "REMIS EN SERVICE"))


# ------------------------------------------------------------------- sauvegarde

def sauvegarder(suffixe, avec_env=False):
    """Tire base, storage et .env de l'ancien back-office vers control-01."""
    sh(CONTROL, f"mkdir -p {TRAVAIL} && chmod 700 {TRAVAIL}", silencieux=True)
    script = open(DUMP, encoding="utf-8").read()
    modes = [("db", f"db-{suffixe}.sql.gz"), ("storage", f"storage-{suffixe}.tar.gz")]
    if avec_env:
        modes.append(("env", "env-ancien"))
    for mode, fichier in modes:
        amont = subprocess.Popen(["ssh", VPS, f"bash -s -- {REPERTOIRE} {mode}"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        aval = subprocess.Popen(["ssh", CONTROL, f"cat > {TRAVAIL}/{fichier}"], stdin=amont.stdout)
        amont.stdin.write(script.encode())
        amont.stdin.close()
        amont.stdout.close()
        aval.communicate()
        if amont.wait() != 0 or aval.returncode != 0:
            sortir(f"sauvegarde « {mode} » en échec")
        taille = sh(CONTROL, f"stat -c %s {TRAVAIL}/{fichier}", silencieux=True).strip()
        print(f"  {fichier} : {taille} octets")
    sh(CONTROL, f"chmod 600 {TRAVAIL}/*", silencieux=True)


def comptes_source():
    """Compte les lignes de CHAQUE table de la base du VPS.

    À n'appeler qu'une fois l'ancien back-office en maintenance : sans cela le
    planificateur écrit dans `instance_checks` toutes les cinq minutes et les comptes
    ne sont plus comparables.
    """
    script = f"""set -euo pipefail
cd {REPERTOIRE}
getenv() {{ sudo -n grep -E "^$1=" .env | head -1 | cut -d= -f2- | sed -e 's/\\r$//' -e 's/^"\\(.*\\)"$/\\1/' -e "s/^'\\(.*\\)'$/\\1/"; }}
export MYSQL_PWD=$(getenv DB_PASSWORD)
U=$(getenv DB_USERNAME); D=$(getenv DB_DATABASE); H=$(getenv DB_HOST); H=${{H:-127.0.0.1}}
for t in $(mysql -N -B -h "$H" -u "$U" -e "SHOW TABLES" "$D"); do
  echo "$t=$(mysql -N -B -h "$H" -u "$U" -e "SELECT COUNT(*) FROM \\`$t\\`" "$D")"
done
"""
    return _lire_comptes(script_distant(VPS, script))


def comptes_cible(app):
    """Compte les lignes de chaque table de la base en conteneur.

    Le mot de passe n'est jamais passé en argument ni depuis le Beelink : le shell du
    conteneur lit la variable que MySQL y a déjà, donc rien n'apparaît dans « ps ».
    """
    # Le script part dans le conteneur par un fichier, jamais par trois niveaux de
    # guillemets imbriqués : c'est la façon dont on se fait avaler une commande en
    # silence. Le mot de passe est lu par le shell DU CONTENEUR dans son propre
    # environnement, il n'apparaît donc ni en argument ni dans « ps ».
    script = f"""set -euo pipefail
cat > /tmp/.comptes-$$.sh <<'SCRIPT'
#!/bin/sh
export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
D="$MYSQL_DATABASE"
for t in $(mysql -N -B -u root -e "SHOW TABLES" "$D"); do
  echo "$t=$(mysql -N -B -u root -e "SELECT COUNT(*) FROM \\`$t\\`" "$D")"
done
SCRIPT
trap 'rm -f /tmp/.comptes-$$.sh' EXIT
docker cp /tmp/.comptes-$$.sh {app}-db-1:/tmp/comptes.sh >/dev/null
docker exec {app}-db-1 sh /tmp/comptes.sh
docker exec {app}-db-1 rm -f /tmp/comptes.sh
"""
    return _lire_comptes(script_distant(CONTROL, script))


def _lire_comptes(sortie):
    comptes = {}
    for ligne in sortie.splitlines():
        ligne = ligne.strip()
        if "=" in ligne:
            cle, valeur = ligne.rsplit("=", 1)
            if valeur.isdigit():
                comptes[cle] = int(valeur)
    return comptes


def verifier_copie(source, cible, strict=True):
    """Refuse d'aller plus loin si la copie ne reproduit pas la source, table par table.

    C'est le garde-fou qui rend la bascule acceptable : à ce stade l'ancien back-office
    est en maintenance mais le DNS n'a pas bougé, donc le retour arrière est un simple
    « php artisan up ».

    `strict=False` sert à la répétition à blanc, où la source tourne encore : le
    planificateur y ajoute des lignes de contrôle d'instances entre la sauvegarde et le
    comptage. Un écart y est alors signalé sans arrêter — SAUF sur les tables du métier,
    qui ne bougent pas toutes seules et dont la moindre différence est un vrai défaut.
    """
    if not cible:
        sortir("impossible de compter les lignes de la base restaurée — opération annulée.")
    communes = sorted((set(source) & set(cible)) - VOLATILES)
    if not communes:
        sortir("aucune table comparable entre la source et la copie — opération annulée. "
               "Les deux comptages doivent employer les mêmes noms de tables.")
    manquantes = sorted(set(source) - set(cible) - VOLATILES)
    print(f"  {len(communes)} tables comparées, "
          f"{sum(cible[t] for t in communes)} lignes au total")
    for t in sorted(METIER & set(communes)):
        print(f"    {t} : {cible[t]}")
    if manquantes:
        sortir("tables absentes de la copie : " + ", ".join(manquantes))

    ecarts = [f"{t} : source {source[t]}, copie {cible[t]}"
              for t in communes if source[t] != cible[t]]
    bloquants = [e for e in ecarts if strict or e.split(" :")[0] in METIER]
    if bloquants:
        sortir("la copie ne correspond pas à la source :\n  - " + "\n  - ".join(bloquants)
               + "\nRIEN N'A BASCULÉ. Remettre l'ancien back-office en service "
                 "(« migrate-backoffice.py service ») et analyser.")
    if ecarts:
        print("  écarts tolérés, la source est encore en service :")
        for e in ecarts:
            print(f"    {e}")
        print("  toutes les tables du métier sont identiques")
    else:
        print("  copie conforme à la source")


# ------------------------------------------------------------------------ .env

def construire_env(image, mot_de_passe, racine):
    """Le .env de l'ancien back-office, adapté au conteneur.

    APP_KEY est conservée telle quelle, et ce n'est pas négociable : elle chiffre les
    réglages en base — jeton de l'API Dokploy, jeton DNS Scaleway, jeton de l'agent de
    métriques — et les `.env` des déploiements. La perdre rendrait le back-office
    incapable de piloter quoi que ce soit.
    """
    ancien = sh(CONTROL, f"cat {TRAVAIL}/env-ancien", silencieux=True)
    sortie, vues = [], set()
    sortie.append(f"GHOSTEO_IMAGE={image}")
    sortie.append(f"DB_PASSWORD={mot_de_passe}")
    sortie.append(f"DB_ROOT_PASSWORD={racine}")
    for ligne in ancien.splitlines():
        s = ligne.strip()
        if not s or s.startswith("#"):
            sortie.append(ligne)
            continue
        cle = s.split("=", 1)[0].strip()
        if cle in RETIRER:
            continue
        if cle in FORCE:
            sortie.append(f"{cle}={FORCE[cle]}")
            vues.add(cle)
            continue
        sortie.append(ligne)
    for cle, valeur in FORCE.items():
        if cle not in vues:
            sortie.append(f"{cle}={valeur}")
    env = "\n".join(sortie).rstrip() + "\n"
    if "APP_KEY=" not in env:
        sortir("APP_KEY absente du .env d'origine — arrêt : les réglages chiffrés "
               "(jetons Dokploy, DNS, métriques) seraient illisibles.")
    return env


# ------------------------------------------------------------------ restauration

def restaurer(app, suffixe):
    """Charge le dump dans la base en conteneur et pose storage/ dans le volume.

    Les conteneurs applicatifs sont arrêtés pendant l'opération : sans cela le
    planificateur écrirait dans la base pendant qu'on la remplace, et les comptes ne
    seraient plus comparables. Le volume est monté sur `storage/`, pas sur
    `storage/app/` : on extrait donc SANS --strip-components.
    """
    script = f"""set -euo pipefail
# L'identifiant du propriétaire est LU dans le conteneur avant de l'arrêter : le
# supposer (33:33 pour www-data) marcherait aujourd'hui et casserait au premier
# changement d'image de base.
U=$(docker exec {app}-web-1 stat -c '%u:%g' /var/www/html/storage)
docker stop {app}-web-1 {app}-scheduler-1 {app}-queue-1 >/dev/null 2>&1 || true
# La base : le mot de passe est lu par le shell DU CONTENEUR dans son propre
# environnement, il n'apparaît donc ni en argument ni dans « ps ».
zcat {TRAVAIL}/db-{suffixe}.sql.gz \\
  | docker exec -i {app}-db-1 sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root "$MYSQL_DATABASE"'
echo "  base restaurée"
# Les fichiers : visuels des publications sociales, documentation Scribe, et surtout
# les DEUX CLÉS des licences hors-ligne (storage/app/private/offline_*.key).
V=$(docker volume inspect {app}_storage --format '{{{{.Mountpoint}}}}')
tar xzf {TRAVAIL}/storage-{suffixe}.tar.gz -C "$V"
chown -R "$U" "$V/app"
du -sh "$V/app" | sed 's/^/  volume : /'
for f in app/private/offline_private.key app/private/offline_public.key; do
  test -f "$V/$f" && echo "  $f présent" || echo "  ATTENTION : $f ABSENT"
done
"""
    print(script_distant(CONTROL, script).rstrip())


def demarrer(app):
    sh(CONTROL, f"docker start {app}-web-1 {app}-scheduler-1 {app}-queue-1", silencieux=True)
    attendre_sain(app=app)


# --------------------------------------------------------------------------- DNS

def dns_lu(nom, serveur, type_="A"):
    return sh(CONTROL, f"dig +short {type_} {nom} @{serveur}", silencieux=True, tolerant=True).strip()


def etat_dns():
    """Ce que répondent le serveur de la zone et trois résolveurs publics."""
    lignes, ok = [], True
    for nom in DOMAINES:
        rep = dns_lu(nom, NS_AUTORITE)
        lignes.append(f"  {nom:18} chez OVH (autorité) : {rep or '(rien)'}")
        if rep != IP_CONTROL:
            ok = False
        for r in RESOLVEURS:
            vu = dns_lu(nom, r)
            lignes.append(f"  {nom:18} vu par {r:8} : {vu or '(rien)'}")
            if vu != IP_CONTROL:
                ok = False
    v6 = dns_lu(DOMAINE, NS_AUTORITE, "AAAA")
    attendu = v6 if v6 else "aucun — c'est ce qu'il faut"
    lignes.append(f"  {DOMAINE:18} AAAA (IPv6)         : {attendu}")
    if v6:
        ok = False
    print("\n".join(lignes))
    return ok, bool(v6)


# ---------------------------------------------------------------------- commandes

def cmd_preparer(a):
    """Tout ce qui est long, fait pendant que l'ancien back-office sert encore."""
    if not a.image:
        sortir("préciser l'image, par exemple "
               "--image ghcr.io/guim31/ghosteoeu-main:main-a1b2c3d")
    if os.path.exists(MARQUE):
        sortir(f"un service existe déjà ({compose_id()}). Le supprimer dans Dokploy "
               f"et effacer {MARQUE} avant de recommencer.")

    etape("Sauvegarde à chaud de l'ancien back-office")
    sauvegarder("chaud", avec_env=True)

    etape("Création du service sur control-01")
    mdp = os.urandom(24).hex()
    racine = os.urandom(24).hex()
    st, p = dokploy("POST", "compose.create", {
        "name": DOMAINE, "appName": "ghosteo-backoffice",
        "description": "Back-office ghosteo.eu, migré depuis le VPS OVH (phase 6).",
        "environmentId": ENV_DOKPLOY, "composeType": "docker-compose", "sourceType": "raw",
        "composeFile": open(COMPOSE, encoding="utf-8").read()})
    if st != 200:
        sortir(f"compose.create (HTTP {st}) : {p}")
    cid, app = p["composeId"], p["appName"]
    os.makedirs(os.path.dirname(MARQUE), exist_ok=True)
    open(MARQUE, "w").write(cid)
    os.chmod(MARQUE, 0o600)
    print(f"  composeId={cid} appName={app}")

    etape("Variables d'environnement (clé de chiffrement d'origine conservée)")
    st, _ = dokploy("POST", "compose.saveEnvironment",
                    {"composeId": cid, "env": construire_env(a.image, mdp, racine),
                     "createEnvFile": True})
    if st != 200:
        sortir(f"compose.saveEnvironment (HTTP {st})")
    print(f"  enregistrées (HTTP {st})")

    # Le domaine n'est PAS déclaré ici. Le déclarer avant la bascule d'adresse fait
    # échouer le défi ACME en boucle et épuise le quota de Let's Encrypt (cinq échecs
    # par nom et par heure), ce qui a coûté trois cabinets le 12/09/2026.
    etape("Déploiement (sans domaine : rien n'est publié)")
    dokploy("POST", "compose.deploy", {"composeId": cid, "title": "Préparation du back-office"})
    attendre_sain(app=app)

    etape("Mise en sommeil du planificateur et de la file de la copie")
    # Deux planificateurs ne doivent jamais tourner ensemble : celui-ci ferait avancer
    # les déploiements et sonderait les instances en double, depuis une base qui n'est
    # pas celle qui fait foi. « unless-stopped » respecte un arrêt manuel.
    sh(CONTROL, f"docker stop {app}-scheduler-1 {app}-queue-1", silencieux=True)
    print("  scheduler et queue arrêtés — ils repartiront à la bascule")

    etape("Restauration des données du jour")
    restaurer(app, "chaud")

    etape("Contrôle de conformité de la copie")
    # Souple : la source tourne encore, son moniteur écrit pendant ce temps. Les tables
    # du métier, elles, doivent correspondre exactement.
    verifier_copie(comptes_source(), comptes_cible(app), strict=False)

    etape("Redémarrage du seul conteneur web")
    sh(CONTROL, f"docker start {app}-web-1", silencieux=True)
    attendre_sain(app=app)
    sh(CONTROL, f"docker exec {app}-web-1 curl -s -o /dev/null -w '  /up : %{{http_code}}\\n' "
                f"http://127.0.0.1:8080/up")
    sh(CONTROL, f"docker exec {app}-web-1 curl -s -o /dev/null -w '  /login : %{{http_code}}\\n' "
                f"-H 'X-Forwarded-Proto: https' http://127.0.0.1:8080/login")

    print("\n  Prêt. L'ancien back-office sert toujours, rien n'est publié.")
    print(f"  Étape suivante, dans le créneau : migrate-backoffice.py basculer")


def cmd_basculer(a):
    cid, app = app_name()

    etape("Mise en maintenance de l'ancien back-office")
    maintenance(True)
    print("  (le planificateur et la file d'attente du VPS sont dès lors en sommeil)")

    etape("Sauvegarde à froid")
    sauvegarder("froid")

    etape("Comptes de la source, base figée")
    source = comptes_source()
    print(f"  {len(source)} tables")

    etape("Restauration")
    restaurer(app, "froid")

    etape("Contrôle de conformité avant toute bascule d'adresse")
    verifier_copie(source, comptes_cible(app))

    etape("Démarrage des trois rôles")
    demarrer(app)
    sh(CONTROL, f"docker exec {app}-web-1 php /var/www/html/artisan migrate:status 2>&1 "
                f"| grep -c Pending | sed 's/^/  migrations en attente : /'", tolerant=True)

    etape("À TOI, chez OVH — c'est le seul geste manuel")
    print(f"""
  Espace client OVH → Web Cloud → Noms de domaine → {DOMAINE} → Zone DNS.

    1. Modifier l'enregistrement  A     {DOMAINE:18} → {IP_CONTROL}
    2. Modifier l'enregistrement  A     www.{DOMAINE:14} → {IP_CONTROL}
    3. SUPPRIMER l'enregistrement AAAA  {DOMAINE:18} (l'IPv6 de l'ancien VPS ;
       control-01 n'en a pas, les visiteurs en IPv6 resteraient sur l'ancien serveur)

  Ne toucher à RIEN d'autre : les MX, le SPF et le CNAME « mail » portent ton courrier.

  Puis, ici :   scripts/migrate-backoffice.py dns

  Retour arrière à tout moment : remettre les deux A sur {IP_VPS}, rétablir l'AAAA,
  puis « migrate-backoffice.py service ». Les instances ne voient rien : elles
  gardent leur licence en cache 12 heures.
""")


def cmd_dns(a):
    cid, app = app_name()

    etape("Propagation des adresses")
    ok, v6 = etat_dns()
    if not ok:
        if v6:
            print("\n  L'enregistrement AAAA existe encore : il doit être SUPPRIMÉ.")
        sortir("les adresses ne sont pas encore toutes à jour. Si tu viens de les "
               "changer, attendre quelques minutes et relancer cette commande. "
               "Rien n'a été déclaré.")
    print("  toutes les réponses pointent vers control-01")

    # Le serveur de noms est à jour, mais pas forcément les résolveurs de Let's Encrypt,
    # qui valident le défi ACME depuis leur propre cache. Sans cette marge, le défi part
    # vers l'ANCIEN serveur, échoue, et consomme le quota de cinq échecs par nom et par
    # heure — ce qui a coûté trois cabinets le 12/09/2026.
    print("  attente de 90 s pour que l'ancienne réponse expire partout…")
    time.sleep(90)

    etape("Déclaration des domaines")
    for hote in DOMAINES:
        st, p = dokploy("POST", "domain.create", {
            "host": hote, "composeId": cid, "serviceName": "web", "port": 8080,
            "https": True, "certificateType": "letsencrypt", "domainType": "compose",
            "path": "/"})
        if st != 200:
            sortir(f"déclaration de {hote} refusée (HTTP {st}) : {p}")
        print(f"  {hote} déclaré")

    # Les étiquettes Traefik du domaine sont posées à la création des conteneurs : sans
    # redéploiement, Traefik ne voit rien. Le redéploiement ne touche pas aux volumes.
    etape("Redéploiement pour poser les étiquettes du routeur")
    dokploy("POST", "compose.redeploy", {"composeId": cid, "title": "Domaines de ghosteo.eu"})
    attendre_sain(app=app)

    etape("Certificat")
    for hote in DOMAINES:
        for _ in range(60):
            code = sh(CONTROL, f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 "
                               f"--resolve {hote}:443:{IP_CONTROL} https://{hote}/up || true",
                      silencieux=True).strip()
            if code == "200":
                print(f"  {hote} : certificat en place, HTTPS à 200")
                break
            time.sleep(5)
        else:
            sortir(f"pas de certificat pour {hote} après 5 minutes. Vérifier le journal : "
                   f"ssh {CONTROL} docker logs dokploy-traefik --tail 50 | grep -i acme. "
                   "Un « too many failed authorizations » signifie que le quota Let's "
                   "Encrypt du nom est épuisé : attendre une heure après le dernier échec.")
    cmd_verifier(a)


def cmd_verifier(a):
    _, app = app_name()
    etape("Vérification du back-office")
    # Chaque contrôle vise l'adresse du serveur, sans passer par un résolveur : une
    # vérification qui interroge le DNS peut mesurer l'ANCIEN serveur et conclure à tort.
    # C'est arrivé deux fois en phase 5.
    for hote in DOMAINES:
        sh(CONTROL, f"""R="--resolve {hote}:443:{IP_CONTROL} --resolve {hote}:80:{IP_CONTROL}"
echo "  {hote} /up          : $(curl -s $R -o /dev/null -w '%{{http_code}}' --max-time 15 https://{hote}/up)"
echo "  {hote} /login       : $(curl -s $R -o /dev/null -w '%{{http_code}}' --max-time 15 https://{hote}/login)"
echo "  {hote} http redirige: $(curl -s $R -o /dev/null -w '%{{http_code}} vers %{{redirect_url}}' --max-time 15 http://{hote}/)"
echo "  {hote} certificat   : $(echo | openssl s_client -connect {IP_CONTROL}:443 -servername {hote} 2>/dev/null | openssl x509 -noout -subject -enddate | tr '\\n' ' ')" """)
    sh(CONTROL, f"""
echo "  API de licence      : $(curl -s -o /dev/null -w '%{{http_code}}' --max-time 15 \\
  --resolve {DOMAINE}:443:{IP_CONTROL} -X POST -H 'Accept: application/json' \\
  https://{DOMAINE}/api/v1/licenses/verify) (422 attendu : la requête est vide, mais la route répond)"
echo "  ressources en https : $(curl -s --max-time 15 --resolve {DOMAINE}:443:{IP_CONTROL} \\
  https://{DOMAINE}/login | grep -c 'https://{DOMAINE}')"
docker exec {app}-web-1 php /var/www/html/artisan migrate:status 2>&1 | grep -c Pending | sed 's/^/  migrations en attente : /'
docker ps --format '  {{{{.Names}}}} {{{{.Status}}}}' | grep {app} || true
free -m | awk 'NR==2 {{printf "  control-01 : %s Mo utilisés sur %s\\n", $3, $2}}'
""", tolerant=True)


def cmd_licences(a):
    """Force les huit instances à revalider leur licence, et lit la preuve côté serveur.

    Une instance ne rappelle le serveur de licences que lorsque son cache expire (12 h
    si la licence est active). Sans forcer, la preuve mettrait une demi-journée à venir.
    """
    _, app = app_name()

    etape("Instances trouvées sur worker-01")
    liste = script_distant(WORKER, r"""set -euo pipefail
for d in /etc/dokploy/compose/*/code; do
  [ -f "$d/.env" ] || continue
  url=$(grep -E '^APP_URL=' "$d/.env" | head -1 | cut -d= -f2- | tr -d '"')
  case "$url" in *ghosteoapp.eu*) ;; *) continue ;; esac
  echo "$(basename $(dirname $d)) ${url#https://}"
done
""")
    instances = [l.split() for l in liste.split("\n") if len(l.split()) == 2]
    if not instances:
        sortir("aucune instance trouvée sur worker-01")
    for app_i, domaine in instances:
        print(f"  {domaine} ({app_i})")

    etape("Oubli du cache de licence et nouvel appel, instance par instance")
    for app_i, domaine in instances:
        script = f"""set -uo pipefail
docker exec {app_i}-web-1 php /var/www/html/artisan tinker \\
  --execute='Cache::forget("ghosteo.license.details");' >/dev/null 2>&1 || true
code=$(docker exec {app_i}-web-1 curl -s -o /dev/null -w '%{{http_code}}' --max-time 25 \\
  -H 'X-Forwarded-Proto: https' -H 'Host: {domaine}' http://127.0.0.1:8080/login || true)
echo "  {domaine} : /login $code"
"""
        print(script_distant(WORKER, script).rstrip())

    etape("Ce que le serveur de licences a enregistré")
    time.sleep(10)
    script = f"""set -euo pipefail
docker exec {app}-db-1 sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -B -u root -e "
SELECT CONCAT(\\"  \\", RPAD(COALESCE(last_verified_url, \\"(jamais)\\"), 46, \\" \\"),
              COALESCE(last_verified_at, \\"(jamais)\\"), \\"   v\\", COALESCE(app_version, \\"?\\"))
FROM licenses ORDER BY last_verified_at DESC;" "$MYSQL_DATABASE"'
"""
    print(script_distant(CONTROL, script).rstrip())
    print("\n  Une date des dernières minutes vaut preuve : l'instance a bien joint le")
    print("  nouveau serveur de licences. Les licences hors-ligne (clé « OFFLINE_ ») ne")
    print("  passent jamais par le réseau et resteront à leur ancienne date.")


def cmd_retour_arriere(a):
    etape("RETOUR ARRIÈRE")
    print(f"""
  Dans cet ordre, et pas l'inverse — rendre l'adresse AVANT de remettre en service,
  sans quoi deux back-offices répondraient selon le cache de chacun.

  1. Chez OVH, zone DNS de {DOMAINE} :
       A     {DOMAINE:18} → {IP_VPS}
       A     www.{DOMAINE:14} → {IP_VPS}
       AAAA  {DOMAINE:18} → 2001:41d0:404:200::9036   (à rétablir)

  2. Ici, quand les adresses sont revenues :
       scripts/migrate-backoffice.py service
""")
    print("  La copie reste en place sur control-01, à analyser à froid.")
    print("  Les instances ne voient rien : leur licence est en cache 12 heures.")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("commande", choices=["preparer", "basculer", "dns", "verifier",
                                        "licences", "retour-arriere",
                                        "maintenance", "service"])
    p.add_argument("--image", help="image à déployer (commande « preparer »)")
    a = p.parse_args()
    print(f"Back-office « {DOMAINE} » — du VPS OVH vers {CONTROL} ({IP_CONTROL})")
    {"preparer": cmd_preparer, "basculer": cmd_basculer, "dns": cmd_dns,
     "verifier": cmd_verifier, "licences": cmd_licences,
     "retour-arriere": cmd_retour_arriere,
     "maintenance": lambda _: maintenance(True),
     "service": lambda _: maintenance(False)}[a.commande](a)


if __name__ == "__main__":
    main()
