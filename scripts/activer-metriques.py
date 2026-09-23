#!/usr/bin/env python3
"""Active l'agent de métriques Dokploy d'un serveur, et dit quoi saisir dans le back-office.

Le moniteur d'instances lit chaque serveur par son agent (`dokploy/monitoring`, port 4500),
à travers le réseau privé `ghosteo-interne`. Trois conditions, dont une seule vient d'office :

1. le pare-feu : `cloud-init/worker.yaml` ouvre déjà le port 4500 au seul réseau privé ;
2. l'agent : Dokploy ne le démarre qu'à l'appel de `server.setupMonitoring` — c'est ce que fait
   ce script, avec la configuration de worker-01 (jeton partagé, relevé toutes les 60 s,
   7 jours de rétention) ;
3. le back-office : l'adresse privée du serveur dans Réglages → Serveurs, champ de l'agent de
   métriques. Le script l'imprime ; la saisie reste un geste de Guilhem.

Oubli constaté le 23/09/2026 : worker-02, attaché à Dokploy le 21/09, n'avait jamais eu
l'étape 2, et le moniteur affichait « Aucun relevé » pour le serveur des essais.

Usage :
  activer-metriques.py worker-02                 active l'agent, vérifie, imprime la marche à suivre
  activer-metriques.py worker-02 --verifier      vérifie seulement (aucune écriture)

Rejouable : appeler setupMonitoring sur un agent déjà actif le reconfigure à l'identique.
control-01 est le serveur du panneau : son agent se règle par admin.setupMonitoring, pas par
server.setupMonitoring, et il n'apparaît pas dans server.all.

Relevé toutes les 15 s, et non 60 : un agent relève le processeur à l'instant, toujours à la
même seconde de la minute. Celui de control-01 tombait au réveil du planificateur Laravel et
affichait 85 % pour une machine inactive à 95 % (23/09/2026). À 15 s, quatre instants par
minute, que le moniteur moyenne sur cinq minutes.
"""
import argparse
import os
import subprocess
import sys
import time

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)
from dokploy import call as dokploy          # noqa: E402

JETON = os.path.expanduser("~/.config/dokploy/metrics.token")
PORT = 4500
PANNEAU = "control-01"
BACKOFFICE = "ghosteo-backoffice-w33xq9-web-1"          # sur control-01


def die(message):
    print(f"ERREUR : {message}", file=sys.stderr)
    sys.exit(1)


def serveur_dokploy(nom):
    if nom == PANNEAU:
        status, reglages = dokploy("GET", "settings.getWebServerSettings")
        if status != 200:
            die(f"settings.getWebServerSettings a répondu {status}")
        return {"serverId": None, "metricsConfig": reglages.get("metricsConfig")}
    status, serveurs = dokploy("GET", "server.all")
    if status != 200:
        die(f"server.all a répondu {status}")
    for serveur in serveurs:
        if serveur["name"] == nom:
            return serveur
    die(f"aucun serveur « {nom} » dans Dokploy ({', '.join(s['name'] for s in serveurs)})")


def adresse_privee(nom):
    """L'adresse du serveur sur ghosteo-interne (172.31.40.0/22), lue sur la machine.

    Elle vient du DHCP du réseau privé : l'IPAM de Scaleway ne la liste pas. L'alias SSH du
    serveur doit exister sur le Beelink (create-server.py le rappelle).
    """
    sortie = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", nom, "hostname -I"],
                            capture_output=True, text=True, timeout=30)
    if sortie.returncode != 0:
        die(f"ssh {nom} impossible : {sortie.stderr.strip()}")
    privees = [a for a in sortie.stdout.split() if a.startswith("172.31.4")]
    if not privees:
        die(f"{nom} n'a pas d'adresse sur ghosteo-interne : le fichier netplan du réseau privé "
            "n'a pas été posé (voir la consigne imprimée par create-server.py)")
    return privees[0]


def configuration(jeton):
    """La configuration de worker-01, relevée le 23/09/2026."""
    url = open(os.path.expanduser("~/.config/dokploy/url")).read().strip()
    return {
        "server": {
            "refreshRate": 15,
            "port": PORT,
            "token": jeton,
            "urlCallback": url.rstrip("/") + "/",
            "retentionDays": 7,
            "cronJob": "0 * * * *",
            "thresholds": {"cpu": 0, "memory": 0},
        },
        "containers": {"refreshRate": 60, "services": {"include": [], "exclude": []}},
    }


def lire_depuis_le_backoffice(ip):
    """Le relevé tel que le moniteur le fera : même lecteur, même jeton, même réseau.

    Le jeton est lu dans les réglages du back-office, jamais passé en ligne de commande.
    """
    code = (
        "$r = app(App\\Services\\Monitoring\\AgentMetricsReader::class)->read("
        f"'{ip}', {PORT}, (string) App\\Models\\Setting::getValue('metrics_agent_token', ''));"
        "echo $r['ok'] ? 'OK cpu='.$r['cpu'].' ram='.$r['ram'].' disque='.$r['disk'] : 'ECHEC '.$r['message'];"
    )
    commande = ["ssh", "control-01",
                # Le code passe par le shell de control-01, entre guillemets doubles : ses $ doivent
                # arriver intacts jusqu'à PHP.
                f"docker exec {BACKOFFICE} php artisan tinker --execute=\"{code.replace('$', chr(92) + '$')}\""]
    sortie = subprocess.run(commande, capture_output=True, text=True, timeout=60)
    lignes = (sortie.stdout or sortie.stderr).strip().splitlines()
    return lignes[-1] if lignes else ""


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("nom", help="nom du serveur, identique chez Scaleway et dans Dokploy")
    p.add_argument("--verifier", action="store_true", help="ne rien écrire, seulement vérifier")
    args = p.parse_args()

    jeton = open(JETON).read().strip()
    serveur = serveur_dokploy(args.nom)
    ip = adresse_privee(args.nom)
    actif = bool((serveur.get("metricsConfig") or {}).get("server", {}).get("token"))
    rythme = (serveur.get("metricsConfig") or {}).get("server", {}).get("refreshRate")
    print(f"{args.nom} : Dokploy {serveur['serverId'] or 'panneau'}, adresse privée {ip}, "
          f"agent {'configuré' if actif else 'non configuré'}" + (f", relevé toutes les {rythme} s" if actif else ""))

    if not args.verifier:
        if serveur["serverId"] is None:
            route, corps = "admin.setupMonitoring", {"metricsConfig": configuration(jeton)}
        else:
            route, corps = "server.setupMonitoring", {"serverId": serveur["serverId"], "metricsConfig": configuration(jeton)}
        status, reponse = dokploy("POST", route, corps)
        if status != 200:
            die(f"{route} a répondu {status} : {reponse}")
        print("Agent configuré par Dokploy ; démarrage du conteneur…")
        time.sleep(20)

    resultat = lire_depuis_le_backoffice(ip)
    print(f"Lecture depuis le back-office : {resultat or '(aucune réponse)'}")
    if not resultat.startswith("OK"):
        die("l'agent ne répond pas encore depuis control-01 ; relancer avec --verifier dans une minute")

    print()
    print("À saisir dans le back-office, Réglages → Serveurs → " + args.nom + " (bas du formulaire) :")
    print(f"  Adresse privée de l'agent de métriques : {ip}")
    print(f"  Port de l'agent : {PORT}")
    print("  (ne pas toucher au champ « Adresse IP » : c'est l'adresse publique, cible des DNS)")


if __name__ == "__main__":
    main()
