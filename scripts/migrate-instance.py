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
CONTROL = "control-01"
ZONE = "ghosteoapp.eu"
COMPOSE = os.path.join(os.path.dirname(ICI), "compose", "instance.yml")
DUMP = os.path.join(ICI, "remote-dump.sh")
ENV_DOKPLOY = "pC_5KlfCgctYLUpawSQS3"   # projet ghosteo, environnement production

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
echo "  source : patients=$(q 'SELECT COUNT(*) FROM ghosteo.patients;') consultations=$(q 'SELECT COUNT(*) FROM ghosteo.consultations;') utilisateurs=$(q 'SELECT COUNT(*) FROM ghosteo.users;')"
APPKEY=$(grep -E '^APP_KEY=' {t}/env-ancien | head -1 | cut -d= -f2- | tr -d '"'"'"'\\r')
[ -n "$APPKEY" ] || {{ echo "APP_KEY introuvable"; exit 1; }}
rm -f {t}/database.sqlite; install -m 666 /dev/null {t}/database.sqlite
docker run --rm --network conv-net --user root -v {t}/database.sqlite:/data/database.sqlite \\
  -e APP_KEY="$APPKEY" -e APP_ENV=production -e APP_DEBUG=false -e AUTORUN_ENABLED=false \\
  -e DB_CONNECTION=sqlite -e DB_DATABASE=/data/database.sqlite \\
  -e SOURCE_DB_HOST=conv-mysql -e SOURCE_DB_PORT=3306 -e SOURCE_DB_DATABASE=ghosteo \\
  -e SOURCE_DB_USERNAME=root -e SOURCE_DB_PASSWORD="$PW" \\
  {c['image']} php /var/www/html/artisan app:copy-database --fresh --no-interaction 2>&1 | tail -2
docker rm -f conv-mysql >/dev/null 2>&1; docker network rm conv-net >/dev/null 2>&1
shred -u {t}/.pw 2>/dev/null || rm -f {t}/.pw
chmod 600 {t}/database.sqlite
"""
    sh(c["worker_ssh"], script)


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
    convertir(c, "chaud")

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
    print("RAPPEL : l'ancienne instance doit être en maintenance (php artisan down) "
          "avant cette étape, sinon les saisies faites depuis sont perdues.")

    etape("Sauvegarde à froid")
    sauvegarder(c, "froid")

    etape("Conversion vers SQLite")
    convertir(c, "froid")

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


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("commande", choices=["ttl", "preparer", "basculer", "verifier"])
    p.add_argument("client")
    a = p.parse_args()
    c = client(a.client)
    print(f"Client « {c['nom']} » — {c['domaine']} vers {c['worker_ssh']}, image {c['image']}")
    {"ttl": cmd_ttl, "preparer": cmd_preparer,
     "basculer": cmd_basculer, "verifier": cmd_verifier}[a.commande](c)


if __name__ == "__main__":
    main()
