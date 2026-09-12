#!/usr/bin/env python3
"""Migration d'une instance GHosteo du VPS OVH vers un worker Dokploy.

Procédure éprouvée sur la démo le 11/09/2026 (voir SUIVI.md, phase 4). L'assistant du
back-office ne convient PAS pour cette opération : il tire une APP_KEY neuve à chaque
déploiement, ce qui rendrait illisibles les dossiers patients. Ce script repart au
contraire du .env de l'ancienne instance et conserve sa clé.

Chaque étape est une sous-commande distincte, à lancer dans cet ordre. Rien n'est
enchaîné automatiquement : la bascule d'un cabinet se décide, elle ne se subit pas.

  1. ttl      <client>            la veille : passe le nom sur un TTL de 60 s
  2. preparer <client>            sauvegarde à chaud, conversion, création et déploiement
                                  de l'instance sur le worker. AUCUNE coupure : l'ancienne
                                  tourne toujours, le certificat échouera, c'est normal.
  3. basculer <client>            le créneau : sauvegarde à froid, conversion, installation
                                  dans le volume, bascule DNS, certificat. ~5 min de coupure.
  4. verifier <client>            contrôles finaux, depuis control-01.

Un « client » est une entrée de clients.yaml (non versionné, voir clients.yaml.exemple).

Avant le premier client : poser `php artisan down` sur l'ancienne instance au début de
l'étape 3 (geste de Guilhem ou autorisation explicite de l'agent), sinon les saisies
faites entre la sauvegarde et la bascule sont perdues.
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
from scw import call as scaleway             # noqa: E402

VPS = "vito@51.178.87.41"
IP_VPS = "51.178.87.41"           # adresse de l'ancien hébergement, cible du retour arrière
CONTROL = "control-01"
ZONE = "ghosteoapp.eu"
COMPOSE = os.path.join(os.path.dirname(ICI), "compose", "instance.yml")
DUMP = os.path.join(ICI, "remote-dump.sh")
ENV_DOKPLOY = "pC_5KlfCgctYLUpawSQS3"   # projet ghosteo, environnement production
BACKOFFICE = "/home/ghosteoserver/ghosteo.eu"
SERVEUR_BACKOFFICE = 2                  # worker-01 dans la table « servers »

# Variables imposées par l'hébergement en conteneur, quelles que soient celles d'origine.
FORCE = {
    "DB_CONNECTION": "sqlite",
    "DB_DATABASE": "/var/www/html/storage/app/database.sqlite",
    "LOG_CHANNEL": "stderr",
    "LOG_STACK": "stderr",
    "QUEUE_CONNECTION": "database",
    "SESSION_DRIVER": "database",
    "CACHE_STORE": "database",
    "TRUSTED_PROXIES": "*",
}
# Variables d'un hébergement mutualisé qui n'ont plus de sens ici.
RETIRER = {
    "DB_HOST", "DB_PORT", "DB_USERNAME", "DB_PASSWORD", "MEMCACHED_HOST",
    "REDIS_CLIENT", "REDIS_HOST", "REDIS_PASSWORD", "REDIS_PORT",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION",
    "AWS_BUCKET", "AWS_USE_PATH_STYLE_ENDPOINT",
}


def clients():
    chemin = os.path.join(os.path.dirname(ICI), "clients.yaml")
    if not os.path.exists(chemin):
        sortir(f"{chemin} absent — copier clients.yaml.exemple et le remplir.")
    conf, courant = {}, None
    for ligne in open(chemin, encoding="utf-8"):
        ligne = ligne.split("#", 1)[0].rstrip()
        if not ligne.strip():
            continue
        if not ligne.startswith(" "):
            courant = ligne.rstrip(":").strip()
            conf[courant] = {}
        else:
            cle, valeur = ligne.split(":", 1)
            conf[courant][cle.strip()] = valeur.strip()
    return conf


def client(nom):
    conf = clients()
    if nom not in conf:
        sortir(f"client « {nom} » inconnu. Connus : {', '.join(conf) or 'aucun'}")
    c = conf[nom]
    for cle in ("domaine", "repertoire", "worker_ssh", "server_id", "image"):
        if cle not in c:
            sortir(f"clients.yaml : « {cle} » manquant pour {nom}")
    c["nom"] = nom
    # Le travail se fait SUR LE WORKER : seul lui peut tirer l'image privée (Dokploy y a
    # posé les identifiants de registre ; control-01 n'en a pas). Les données de santé ne
    # transitent donc ni par le Beelink ni par le serveur de contrôle.
    c["travail"] = f"/root/migration-{nom}"
    return c


def utilisateur(c):
    """L'utilisateur isolé du site sur le VPS, déduit de /home/<utilisateur>/<domaine>."""
    parties = c["repertoire"].strip("/").split("/")
    if len(parties) < 2 or parties[0] != "home":
        sortir(f"répertoire inattendu, utilisateur indéductible : {c['repertoire']}")
    return parties[1]


def maintenance(c, activer):
    """Met l'ancienne instance en maintenance, ou la remet en service.

    Sans ce geste, tout ce qu'un praticien saisit entre la sauvegarde et la bascule est
    perdu. C'est aussi le retour arrière : « php artisan up » remet l'ancienne en service
    tant que le DNS n'a pas bougé.
    """
    u = utilisateur(c)
    action = "down --retry=120" if activer else "up"
    repertoire = c["repertoire"]
    # Le script part par l'entrée standard : imbriquer des guillemets dans
    # « ssh sudo bash -c php artisan » a déjà avalé une commande en silence.
    script = ("set -euo pipefail\n"
              "sudo -n -u " + u + " bash -c 'cd " + repertoire + " && php artisan " + action + "'\n")
    p_ = subprocess.run(["ssh", "-o", "ConnectTimeout=15", VPS, "bash -s"],
                        input=script, capture_output=True, text=True)
    if p_.returncode != 0:
        sortir("« php artisan " + action + " » a échoué sur l'ancienne instance :\n" + p_.stderr[:400])
    print("  ancienne instance " + ("en maintenance" if activer else "REMISE EN SERVICE"))


def sortir(message):
    print("ERREUR :", message, file=sys.stderr)
    sys.exit(1)


def sh(cible, commande, entree=None, silencieux=False):
    """Commande shell sur une machine distante ; sort en erreur si elle échoue."""
    p = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=15", cible, commande],
        input=entree, capture_output=True, text=(entree is None or isinstance(entree, str)),
    )
    if p.returncode != 0:
        sortir(f"{cible} : {commande[:60]}…\n{p.stderr[:800] if isinstance(p.stderr, str) else p.stderr[:800]}")
    if not silencieux and p.stdout:
        print(p.stdout.rstrip())
    return p.stdout


def etape(titre):
    print(f"\n\033[1m— {titre}\033[0m")


# --------------------------------------------------------------------------- DNS

def dns_set(nom, ip, ttl):
    sous_domaine = nom.replace("." + ZONE, "")
    st, p = scaleway(
        "PATCH", f"/domain/v2beta1/dns-zones/{ZONE}/records",
        {"changes": [{"set": {
            "id_fields": {"name": sous_domaine, "type": "A"},
            "records": [{"name": sous_domaine, "type": "A", "data": ip, "ttl": ttl}],
        }}], "return_all_records": False},
    )
    if not 200 <= st < 300:
        sortir(f"DNS refusé (HTTP {st}) : {p}")
    print(f"  {nom} → {ip} (TTL {ttl} s)")


def dns_lu(nom):
    return sh(CONTROL, f"dig +short +norecurse A {nom} @ns0.dom.scw.cloud", silencieux=True).strip()


def cmd_ttl(c):
    """Abaisse le TTL sans rien changer d'autre : à faire la veille."""
    etape(f"TTL de {c['domaine']} abaissé à 60 s (adresse inchangée)")
    actuelle = dns_lu(c["domaine"]) or sh(
        CONTROL, f"dig +short A {c['domaine']} @8.8.8.8", silencieux=True).strip().splitlines()[0]
    dns_set(c["domaine"], actuelle, 60)
    print("  Attendre au moins une heure avant l'étape « basculer » :")
    print("  les résolveurs gardent l'ancienne réponse jusqu'à l'expiration de son TTL.")


# ------------------------------------------------------------------- sauvegarde

def sauvegarder(c, suffixe):
    """Tire base, storage et .env de l'ancienne instance vers le worker."""
    hote = c["worker_ssh"]
    sh(hote, f"mkdir -p {c['travail']} && chmod 700 {c['travail']}", silencieux=True)
    script = open(DUMP, encoding="utf-8").read()
    for mode, fichier in (("db", f"db-{suffixe}.sql.gz"),
                          ("storage", f"storage-{suffixe}.tar.gz"),
                          ("env", "env-ancien")):
        if mode == "env" and suffixe != "chaud":
            continue
        amont = subprocess.Popen(
            ["ssh", VPS, f"bash -s -- {c['repertoire']} {mode}"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        aval = subprocess.Popen(
            ["ssh", hote, f"cat > {c['travail']}/{fichier}"], stdin=amont.stdout)
        amont.stdin.write(script.encode())
        amont.stdin.close()
        amont.stdout.close()
        aval.communicate()
        if amont.wait() != 0 or aval.returncode != 0:
            sortir(f"sauvegarde « {mode} » en échec")
        taille = sh(hote, "stat -c %s " + c["travail"] + "/" + fichier, silencieux=True).strip()
        print(f"  {fichier} : {taille} octets")
    sh(hote, f"chmod 600 {c['travail']}/*", silencieux=True)


def convertir(c, suffixe):
    """Charge le dump dans un MySQL jetable et le recopie en SQLite, clé d'origine conservée."""
    t = c["travail"]
    script = f"""set -euo pipefail
docker rm -f conv-mysql >/dev/null 2>&1 || true
docker network create conv-net >/dev/null 2>&1 || true
openssl rand -hex 16 > {t}/.pw && chmod 600 {t}/.pw
PW=$(cat {t}/.pw)
# mysql:8.4 refuse --default-authentication-plugin (option supprimée) et n'accepte root
# que par TCP, pas par socket.
docker run -d --name conv-mysql --network conv-net -e MYSQL_ROOT_PASSWORD="$PW" \\
  -e MYSQL_DATABASE=ghosteo mysql:8.4 --innodb-buffer-pool-size=128M --performance-schema=OFF >/dev/null
for i in $(seq 1 150); do
  docker exec -e MYSQL_PWD="$PW" conv-mysql mysqladmin -uroot --protocol=TCP -h127.0.0.1 ping >/dev/null 2>&1 && break
  sleep 2
done
docker exec -e MYSQL_PWD="$PW" conv-mysql mysqladmin -uroot --protocol=TCP -h127.0.0.1 ping >/dev/null
zcat {t}/db-{suffixe}.sql.gz | docker exec -i -e MYSQL_PWD="$PW" conv-mysql mysql -uroot --protocol=TCP -h127.0.0.1 ghosteo
q() {{ docker exec -e MYSQL_PWD="$PW" conv-mysql mysql -uroot --protocol=TCP -h127.0.0.1 -N -e "$1"; }}
echo "  source : patients=$(q 'SELECT COUNT(*) FROM ghosteo.patients;') consultations=$(q 'SELECT COUNT(*) FROM ghosteo.consultations;') users=$(q 'SELECT COUNT(*) FROM ghosteo.users;')"
APPKEY=$(grep -E '^APP_KEY=' {t}/env-ancien | head -1 | cut -d= -f2- | tr -d '"'"'"'\\r')
[ -n "$APPKEY" ] || {{ echo "APP_KEY introuvable"; exit 1; }}
rm -f {t}/database.sqlite; install -m 666 /dev/null {t}/database.sqlite
# Les secrets passent par un fichier en mode 600, JAMAIS par la ligne de commande :
# « docker run -e CLE=valeur » expose la valeur dans /proc/<pid>/cmdline, donc a tout
# « ps » lance sur la machine pendant la conversion.
umask 077
cat > {t}/.env-conv <<ENVFILE
APP_KEY=$APPKEY
APP_ENV=production
APP_DEBUG=false
AUTORUN_ENABLED=false
DB_CONNECTION=sqlite
DB_DATABASE=/data/database.sqlite
SOURCE_DB_HOST=conv-mysql
SOURCE_DB_PORT=3306
SOURCE_DB_DATABASE=ghosteo
SOURCE_DB_USERNAME=root
SOURCE_DB_PASSWORD=$PW
ENVFILE
docker run --rm --network conv-net --user root -v {t}/database.sqlite:/data/database.sqlite \\
  --env-file {t}/.env-conv \\
  {c['image']} php /var/www/html/artisan app:copy-database --fresh --no-interaction 2>&1 | tail -2
shred -u {t}/.env-conv 2>/dev/null || rm -f {t}/.env-conv
docker rm -f conv-mysql >/dev/null 2>&1; docker network rm conv-net >/dev/null 2>&1
shred -u {t}/.pw 2>/dev/null || rm -f {t}/.pw
chmod 600 {t}/database.sqlite
"""
    sortie = sh(c["worker_ssh"], script)
    # Comptes de la base MySQL source, imprimés par le script ci-dessus.
    source = {}
    for ligne in sortie.splitlines():
        if "source :" in ligne:
            for morceau in ligne.split("source :", 1)[1].split():
                if "=" in morceau:
                    cle, valeur = morceau.split("=", 1)
                    if valeur.isdigit():
                        source[cle] = int(valeur)
    return source


def comptes_sqlite(c, chemin):
    """Comptes lus dans le fichier SQLite produit, avant toute installation."""
    php = ('foreach (["patients","consultations","users"] as $t) '
           '{ echo $t."=".DB::table($t)->count()." "; } echo PHP_EOL;')
    sortie = sh(c["worker_ssh"],
                f'docker run --rm --user root -v {chemin}:/data/db.sqlite '
                f'-e DB_CONNECTION=sqlite -e DB_DATABASE=/data/db.sqlite -e AUTORUN_ENABLED=false '
                f'-e APP_KEY=base64:{"A" * 43}= {c["image"]} '
                f"php /var/www/html/artisan tinker --execute='{php}' 2>/dev/null | grep patients=",
                silencieux=True)
    comptes = {}
    for morceau in sortie.split():
        if "=" in morceau:
            cle, valeur = morceau.split("=", 1)
            if valeur.isdigit():
                comptes[cle] = int(valeur)
    return comptes


def verifier_conversion(c, source):
    """Refuse d'aller plus loin si la copie ne reproduit pas la source, table par table.

    C'est le garde-fou qui rend une bascule non surveillée acceptable : à ce stade
    l'ancienne instance est en maintenance mais le DNS n'a pas bougé, donc le retour
    arrière est un simple « php artisan up ».
    """
    cible = comptes_sqlite(c, f"{c['travail']}/database.sqlite")
    if not cible:
        sortir("impossible de compter les lignes de la base convertie — bascule annulée.")
    communes = sorted(set(source) & set(cible))
    if not communes:
        sortir("aucune table comparable entre la source et la copie — bascule annulée. "
               "Les deux comptages doivent employer les mêmes noms de tables.")
    ecarts = [f"{k} : source {source[k]}, copie {cible[k]}"
              for k in communes if source[k] != cible[k]]
    ignorees = sorted(set(source) ^ set(cible))
    if ignorees:
        print(f"  (non comparé, faute de correspondance : {', '.join(ignorees)})")
    for cle in communes:
        print(f"  {cle} : {cible[cle]} (source {source[cle]})")
    if ecarts:
        sortir("la copie ne correspond pas à la source :\n  - " + "\n  - ".join(ecarts)
               + "\nRIEN N'A ÉTÉ BASCULÉ. Remettre l'ancienne instance en service par "
                 "« php artisan up » et analyser.")
    print("  copie conforme à la source")


# ------------------------------------------------------------------ Dokploy

def construire_env(c):
    """Le .env de l'ancienne instance, adapté au conteneur. La clé de chiffrement est conservée."""
    ancien = sh(c["worker_ssh"], f"cat {c['travail']}/env-ancien", silencieux=True)
    sortie, vues = [f"GHOSTEO_IMAGE={c['image']}"], set()
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
        if cle == "APP_URL":
            sortie.append(f"APP_URL=https://{c['domaine']}")
            vues.add(cle)
            continue
        sortie.append(ligne)
    for cle, valeur in FORCE.items():
        if cle not in vues:
            sortie.append(f"{cle}={valeur}")
    env = "\n".join(sortie).rstrip() + "\n"
    if "APP_KEY=" not in env:
        sortir("APP_KEY absente du .env d'origine — arrêt : les dossiers seraient illisibles.")
    return env


def cmd_preparer(c):
    """Tout ce qui est long, fait pendant que l'ancienne instance tourne encore."""
    etape("Sauvegarde à chaud de l'ancienne instance")
    sauvegarder(c, "chaud")

    etape("Conversion d'essai vers SQLite (valide la chaîne avant toute coupure)")
    source = convertir(c, "chaud")
    verifier_conversion(c, source)

    etape("Création du service sur le worker")
    st, p = dokploy("POST", "compose.create", {
        "name": c["domaine"], "appName": f"ghosteo-{c['nom']}",
        "description": f"Instance migrée depuis le VPS OVH ({c['nom']}).",
        "environmentId": ENV_DOKPLOY, "composeType": "docker-compose", "sourceType": "raw",
        "composeFile": open(COMPOSE, encoding="utf-8").read(), "serverId": c["server_id"]})
    if st != 200:
        sortir(f"compose.create (HTTP {st}) : {p}")
    cid = p["composeId"]
    print(f"  composeId={cid} appName={p['appName']}")
    open(os.path.expanduser(f"~/.config/dokploy/{c['nom']}.composeId"), "w").write(cid)

    etape("Variables d'environnement (clé de chiffrement d'origine conservée)")
    st, _ = dokploy("POST", "compose.saveEnvironment",
                    {"composeId": cid, "env": construire_env(c), "createEnvFile": True})
    print(f"  enregistrées (HTTP {st})")

    etape("Domaine et certificat")
    st, _ = dokploy("POST", "domain.create", {
        "host": c["domaine"], "composeId": cid, "serviceName": "web", "port": 8080,
        "https": True, "certificateType": "letsencrypt", "domainType": "compose", "path": "/"})
    print(f"  déclaré (HTTP {st}) — le certificat échouera tant que le DNS pointe ailleurs, c'est normal")

    etape("Déploiement")
    dokploy("POST", "compose.deploy", {"composeId": cid, "title": f"Migration {c['nom']}"})
    attendre_conteneur(c)
    print("\n  Prêt. L'ancienne instance sert toujours les clients.")
    print(f"  Étape suivante, dans le créneau convenu : migrate-instance.py basculer {c['nom']}")


def app_name(c):
    cid = open(os.path.expanduser(f"~/.config/dokploy/{c['nom']}.composeId")).read().strip()
    st, p = dokploy("GET", "compose.one", query={"composeId": cid})
    return cid, p["appName"]


def attendre_conteneur(c, minutes=10):
    _, app = app_name(c)
    for _ in range(minutes * 6):
        etat = sh(c["worker_ssh"],
                  f"docker ps --format '{{{{.Names}}}} {{{{.Status}}}}' | grep {app}-web-1 || true",
                  silencieux=True)
        if "healthy" in etat:
            print(f"  conteneurs en service : {etat.strip()}")
            return
        time.sleep(10)
    sortir("le conteneur web n'est pas devenu sain dans le délai imparti")


def cmd_basculer(c):
    """Le créneau : coupure de quelques minutes."""
    _, app = app_name(c)
    etape("Mise en maintenance de l'ancienne instance")
    maintenance(c, True)

    etape("Sauvegarde à froid")
    sauvegarder(c, "froid")

    etape("Conversion vers SQLite")
    source = convertir(c, "froid")

    etape("Contrôle de la copie avant toute bascule")
    verifier_conversion(c, source)

    etape("Installation dans le volume de la nouvelle instance")
    # Tout est déjà sur le worker : aucune copie ne passe par le Beelink.
    # Le volume est monté sur storage/, pas sur storage/app/ : extraire SANS strip-components,
    # sinon hardware_id atterrit au mauvais niveau et la licence repart sur une empreinte neuve.
    sh(c["worker_ssh"], f"""set -euo pipefail
T={c['travail']}
V=$(docker volume inspect {app}_storage --format '{{{{.Mountpoint}}}}')
U=$(docker exec {app}-web-1 stat -c '%u:%g' /var/www/html/storage/app/database.sqlite)
docker stop {app}-web-1 {app}-scheduler-1 {app}-queue-1 >/dev/null
cp "$T/database.sqlite" "$V/app/database.sqlite"
rm -f "$V/app/database.sqlite-wal" "$V/app/database.sqlite-shm"
tar xzf "$T/storage-froid.tar.gz" -C "$V"
chown -R "$U" "$V/app"
docker start {app}-web-1 {app}-scheduler-1 {app}-queue-1 >/dev/null
test -f "$V/app/hardware_id" && echo "  hardware_id conservé" || echo "  ATTENTION : hardware_id absent"
du -sh "$V/app" | sed 's/^/  volume : /'
""")
    attendre_conteneur(c)

    etape("Bascule de l'adresse")
    ip = sh(c["worker_ssh"], "curl -s --max-time 10 https://ifconfig.me", silencieux=True).strip()
    dns_set(c["domaine"], ip, 60)
    for _ in range(60):
        if dns_lu(c["domaine"]) == ip:
            break
        time.sleep(5)
    print(f"  serveur de noms à jour : {c['domaine']} → {ip}")

    etape("Certificat")
    # Traefik cesse de retenter après les échecs d'avant la bascule : le redémarrage relance.
    sh(c["worker_ssh"], "docker restart dokploy-traefik >/dev/null && echo '  Traefik redémarré'")
    for _ in range(60):
        code = sh(CONTROL, f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 https://{c['domaine']}/up || true",
                  silencieux=True).strip()
        if code == "200":
            print("  certificat en place, l'instance répond en HTTPS")
            break
        time.sleep(5)
    else:
        sortir("pas de certificat après 5 minutes — vérifier le journal de dokploy-traefik")
    cmd_verifier(c)


def cmd_retour_arriere(c):
    """Remet le client sur son ancienne instance : adresse puis sortie de maintenance.

    Dans cet ordre, et pas l'inverse : sortir l'ancienne de maintenance avant de rendre
    l'adresse ferait servir deux instances différentes selon le cache du visiteur.
    """
    etape("RETOUR ARRIÈRE")
    dns_set(c["domaine"], IP_VPS, 60)
    for _ in range(60):
        if dns_lu(c["domaine"]) == IP_VPS:
            break
        time.sleep(5)
    print(f"  adresse rendue à l'ancien serveur : {c['domaine']} → {IP_VPS}")
    maintenance(c, False)
    code = sh(CONTROL, f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 15 "
                       f"https://{c['domaine']}/login || true", silencieux=True).strip()
    print(f"  l'ancienne instance répond : {code}")
    print("  La nouvelle instance reste en place sur le worker, à analyser à froid.")


def cmd_verifier(c):
    """Contrôles finaux, depuis control-01 : le résolveur de la maison ment."""
    _, app = app_name(c)
    etape("Vérification")
    sh(CONTROL, f"""echo "  adresse   : $(dig +short A {c['domaine']} @8.8.8.8)"
echo "  /up       : $(curl -s -o /dev/null -w '%{{http_code}}' --max-time 15 https://{c['domaine']}/up)"
echo "  /login    : $(curl -s -o /dev/null -w '%{{http_code}}' --max-time 15 https://{c['domaine']}/login)"
echo "  http      : $(curl -s -o /dev/null -w '%{{http_code}} vers %{{redirect_url}}' --max-time 15 http://{c['domaine']}/)"
echo "  servi par : $(curl -s -o /dev/null -w '%{{remote_ip}}' --max-time 15 https://{c['domaine']}/up)"
echo "  certificat: $(echo | openssl s_client -connect {c['domaine']}:443 -servername {c['domaine']} 2>/dev/null | openssl x509 -noout -enddate)" """)
    sh(c["worker_ssh"], f"""docker exec {app}-web-1 php /var/www/html/artisan tinker --execute='
echo "  patients=".DB::table("patients")->count()." consultations=".DB::table("consultations")->count()." utilisateurs=".DB::table("users")->count().PHP_EOL;
echo "  dechiffrement : ".(\\App\\Models\\Patient::orderBy("id")->first()->nom ?? "AUCUN PATIENT").PHP_EOL;
' 2>&1 | tail -2
test -f "$(docker volume inspect {app}_storage --format '{{{{.Mountpoint}}}}')/app/hardware_id" && echo "  hardware_id conservé" || echo "  ATTENTION : hardware_id absent"
docker exec {app}-web-1 php /var/www/html/artisan migrate:status 2>&1 | grep -c Pending | sed 's/^/  migrations en attente : /'""")
    print(f"\n  Comparer les comptes ci-dessus avec l'ancienne instance AVANT de déclarer la migration réussie.")
    print(f"  L'ancienne instance reste intacte sur le VPS pendant 30 jours.")


def cmd_backoffice(c):
    """Rattache l'instance à son nouveau serveur dans le back-office ghosteo.eu.

    Le PHP part par l'entrée standard d'un script, jamais dans une chaîne de commande :
    imbriquer des guillemets dans « ssh sudo bash -c php artisan tinker --execute » est
    ingérable et a déjà avalé silencieusement deux commandes.
    """
    cid, _ = app_name(c)
    ip = sh(c["worker_ssh"], "curl -s --max-time 10 https://ifconfig.me", silencieux=True).strip()
    etape("Rattachement dans le back-office")
    script = f"""set -euo pipefail
cat > /tmp/.rattache-$$.php <<'PHP'
<?php
$i = \\App\\Models\\Instance::where('url', 'like', '%{c["domaine"]}%')->first();
if (! $i) {{ echo 'INSTANCE INTROUVABLE POUR {c["domaine"]}', PHP_EOL; exit(1); }}
$i->server_id = {SERVEUR_BACKOFFICE};
$i->dokploy_compose_id = '{cid}';
$i->ip = '{ip}';
$i->vito_server_id = null;
$i->vito_site_id = null;
$i->save();
echo 'instance #', $i->id, ' ', $i->name, ' -> serveur ', $i->server_id, PHP_EOL;
PHP
chmod 644 /tmp/.rattache-$$.php
trap 'rm -f /tmp/.rattache-$$.php' EXIT
sudo -n -u ghosteoserver bash -c "cd {BACKOFFICE} && php artisan tinker /tmp/.rattache-$$.php" 2>/dev/null | grep -E 'instance #|INTROUVABLE' | sed 's/^/  /'
"""
    p_ = subprocess.run(["ssh", "-o", "ConnectTimeout=15", VPS, "bash -s"],
                        input=script, capture_output=True, text=True)
    sortie = (p_.stdout or "").strip()
    print(sortie or "  (aucune réponse du back-office)")
    if "INTROUVABLE" in sortie or not sortie:
        sortir("rattachement au back-office impossible — à faire à la main.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("commande", choices=["ttl", "preparer", "basculer", "verifier",
                                       "maintenance", "service", "backoffice",
                                       "retour-arriere"])
    p.add_argument("client")
    a = p.parse_args()
    c = client(a.client)
    print(f"Client « {c['nom']} » — {c['domaine']} vers {c['worker_ssh']}, image {c['image']}")
    {"ttl": cmd_ttl, "preparer": cmd_preparer, "basculer": cmd_basculer,
     "verifier": cmd_verifier, "backoffice": cmd_backoffice,
     "maintenance": lambda x: maintenance(x, True),
     "service": lambda x: maintenance(x, False),
     "retour-arriere": cmd_retour_arriere}[a.commande](c)


if __name__ == "__main__":
    main()
