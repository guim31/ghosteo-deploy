#!/usr/bin/env python3
"""Crée un serveur GHosteo chez Scaleway, de façon reproductible.

  create-server.py control-01 DEV1-M cloud-init/control.yaml [--panel-from IP]
  create-server.py worker-01 DEV1-L cloud-init/worker.yaml --ssh-from 51.158.96.49 \
      --ssh-from 82.66.175.113 --authorized-key dokploy.pub

Ce que fait le script, dans l'ordre, et sans rien refaire si ça existe déjà :
  1. groupe de sécurité « ghosteo-<rôle> » : tout refusé en entrée sauf 22, 80, 443 ;
     avec --ssh-from (répétable), le port 22 n'est ouvert qu'à ces adresses (panneau,
     maison) au lieu de tout Internet ; avec --panel-from, le port 3000 (panneau
     Dokploy en clair) n'est ouvert qu'à cette adresse ;
  2. une adresse IP fixe (« flexible ») au nom du serveur, pour que l'IP survive à une
     recréation de la machine ;
  3. la machine, sur Ubuntu 24.04, disque local de 40 Go, avec la clé SSH publique du
     Beelink passée en tag AUTHORIZED_KEY (la section « users » de cloud-init n'est pas
     appliquée à root sur les images Scaleway ; le tag, lui, est lu à chaque démarrage) ;
     --authorized-key FICHIER (répétable) ajoute d'autres clés publiques de la même
     façon, par exemple la clé dédiée générée par Dokploy pour piloter un worker ;
  4. le cloud-init injecté comme user_data, PUIS le démarrage ;
  5. avec --reseau-prive <id>, une carte sur le réseau privé Scaleway, par laquelle
     le back-office lira les métriques du serveur. Le système la configure seul via
     le fichier netplan posé par le cloud-init.

Après création, l'interface privée ne prend son adresse que si le cloud-init a posé
son fichier netplan : vérifier `ip -4 -br addr` et, au besoin, relancer `netplan apply`.

Le rôle est le mot avant le tiret du nom (control-01 → control). Aucun secret : la clé
d'API est lue par scw.py dans ~/.config/scw/config.yaml.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scw import call, load_config  # noqa: E402

ZONE = "fr-par-1"
BASE = f"/instance/v1/zones/{ZONE}"
UBUNTU_LABEL = "ubuntu_noble"
ROOT_SIZE = 40_000_000_000  # 40 Go, plafond du disque local des DEV1
SSH_PUBKEY = os.path.expanduser("~/.ssh/id_ed25519.pub")


def authorized_key_tag(path=SSH_PUBKEY, comment=None):
    """Tag Scaleway AUTHORIZED_KEY : la clé publique, espaces remplacés par des « _ »."""
    with open(path) as fh:
        parts = fh.read().split()
    kind, key = parts[:2]
    comment = comment or (parts[2] if len(parts) > 2 else "beelink-claude")
    return f"AUTHORIZED_KEY={kind}_{key}_{comment}"


def die(msg, payload=None):
    print("ERREUR :", msg, file=sys.stderr)
    if payload is not None:
        print(json.dumps(payload, indent=2, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)


def ok(status, payload, what):
    if not 200 <= status < 300:
        die(f"{what} (HTTP {status})", payload)
    return payload


def find_image(commercial_type):
    status, payload = call(
        "GET",
        f"/marketplace/v2/local-images?image_label={UBUNTU_LABEL}&zone={ZONE}"
        "&type=instance_local&per_page=50",
    )
    ok(status, payload, "liste des images")
    for img in payload["local_images"]:
        if img["arch"] == "x86_64" and commercial_type in img["compatible_commercial_types"]:
            return img["id"]
    die(f"aucune image {UBUNTU_LABEL} compatible avec {commercial_type}")


def ensure_security_group(project, role, panel_from, ssh_from=()):
    name = f"ghosteo-{role}"
    status, payload = call("GET", f"{BASE}/security_groups?project={project}&name={name}")
    ok(status, payload, "liste des groupes de sécurité")
    existing = [g for g in payload["security_groups"] if g["name"] == name]
    if existing:
        sg = existing[0]
        print(f"groupe de sécurité {name} existant : {sg['id']}")
    else:
        status, payload = call(
            "POST",
            f"{BASE}/security_groups",
            {
                "name": name,
                "project": project,
                "description": f"GHosteo {role} : 22/80/443 seulement, 3000 restreint",
                "stateful": True,
                "inbound_default_policy": "drop",
                "outbound_default_policy": "accept",
            },
        )
        sg = ok(status, payload, "création du groupe de sécurité")["security_group"]
        print(f"groupe de sécurité {name} créé : {sg['id']}")

    wanted = [("TCP", 22, f"{ip}/32") for ip in ssh_from] or [("TCP", 22, None)]
    wanted += [
        ("TCP", 80, None),
        ("TCP", 443, None),
        ("UDP", 443, None),
        ("ICMP", None, None),
    ]
    if panel_from:
        wanted.append(("TCP", 3000, f"{panel_from}/32"))

    status, payload = call("GET", f"{BASE}/security_groups/{sg['id']}/rules?per_page=100")
    rules = ok(status, payload, "règles du groupe")["rules"]
    have = {(r["protocol"], r.get("dest_port_from"), r["ip_range"]) for r in rules}
    for proto, port, ip_range in wanted:
        key = (proto, port, ip_range or "0.0.0.0/0")
        if key in have:
            continue
        body = {
            "protocol": proto,
            "direction": "inbound",
            "action": "accept",
            "ip_range": ip_range or "0.0.0.0/0",
        }
        if port:
            body["dest_port_from"] = port
        status, payload = call("POST", f"{BASE}/security_groups/{sg['id']}/rules", body)
        ok(status, payload, f"règle {proto} {port} {ip_range}")
        print(f"  règle ajoutée : {proto} {port or ''} depuis {body['ip_range']}")
    return sg["id"]


def ensure_ip(project, name):
    status, payload = call("GET", f"{BASE}/ips?project={project}&per_page=100")
    ips = ok(status, payload, "liste des IP")["ips"]
    for ip in ips:
        if name in ip.get("tags", []) and ip["type"] == "routed_ipv4":
            print(f"IP fixe existante : {ip['address']}")
            return ip
    status, payload = call(
        "POST", f"{BASE}/ips", {"project": project, "type": "routed_ipv4", "tags": [name]}
    )
    ip = ok(status, payload, "réservation de l'IP")["ip"]
    print(f"IP fixe réservée : {ip['address']}")
    return ip


def find_server(project, name):
    status, payload = call("GET", f"{BASE}/servers?project={project}&name={name}")
    for srv in ok(status, payload, "liste des serveurs")["servers"]:
        if srv["name"] == name:
            return srv
    return None


def put_user_data(server_id, cloud_init_path):
    cfg = load_config()
    with open(cloud_init_path, "rb") as fh:
        data = fh.read()
    req = urllib.request.Request(
        f"https://api.scaleway.com{BASE}/servers/{server_id}/user_data/cloud-init",
        data=data,
        method="PATCH",
        headers={"X-Auth-Token": cfg["secret_key"], "Content-Type": "text/plain"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        if resp.status not in (200, 204):
            die(f"user_data refusé (HTTP {resp.status})")
    print("cloud-init injecté")


def attacher_reseau_prive(server_id, private_network_id):
    """Rattache le serveur au réseau privé, par lequel passent les relevés de métriques.

    Le chemin est `/servers/<id>/private_nics` ; `/private_nics` seul renvoie 404.
    """
    status, payload = call(
        "GET", f"{BASE}/servers/{server_id}/private_nics")
    existantes = ok(status, payload, "cartes privées du serveur")["private_nics"]
    if any(n.get("private_network_id") == private_network_id for n in existantes):
        print("réseau privé déjà rattaché")
        return

    status, payload = call(
        "POST", f"{BASE}/servers/{server_id}/private_nics",
        {"private_network_id": private_network_id, "tags": ["metriques"]})
    nic = ok(status, payload, "rattachement au réseau privé")["private_nic"]
    print(f"carte privée créée : {nic['id']} ({nic['mac_address']})")
    # Le cloud-init ne peut pas connaître cette adresse MAC avant que la carte existe :
    # le fichier netplan se pose après coup. Les deux dérogations DHCP ne sont pas
    # optionnelles — sans elles, le réseau privé installerait une route par défaut et
    # remplacerait la résolution DNS du serveur.
    print(f"""
À exécuter sur la machine pour qu'elle prenne son adresse privée :

  cat > /etc/netplan/60-reseau-prive.yaml <<'EOF'
  network:
    version: 2
    ethernets:
      reseau-prive:
        match:
          macaddress: "{nic['mac_address']}"
        dhcp4: true
        dhcp4-overrides:
          use-routes: false
          use-dns: false
        dhcp6: false
  EOF
  chmod 600 /etc/netplan/60-reseau-prive.yaml && netplan apply
  ip -4 -br addr | grep -v ens2   # doit montrer une adresse en 172.31.40.x
""")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", help="ex. control-01, worker-01")
    parser.add_argument("commercial_type", help="ex. DEV1-M, DEV1-L")
    parser.add_argument("cloud_init", help="fichier #cloud-config à injecter")
    parser.add_argument("--panel-from", help="IP autorisée sur le port 3000 (panneau Dokploy)")
    parser.add_argument("--ssh-from", action="append", default=[],
                        help="IP autorisée sur le port 22 (répétable) ; sans elle, 22 ouvert à tous")
    parser.add_argument("--authorized-key", action="append", default=[],
                        help="fichier de clé publique supplémentaire à poser en tag AUTHORIZED_KEY (répétable)")
    parser.add_argument("--reseau-prive",
                        help="identifiant du réseau privé Scaleway à rattacher (métriques)")
    args = parser.parse_args()

    cfg = load_config()
    project = cfg["default_project_id"]
    role = args.name.split("-")[0]

    sg_id = ensure_security_group(project, role, args.panel_from, args.ssh_from)
    ip = ensure_ip(project, args.name)

    server = find_server(project, args.name)
    if server:
        print(f"serveur {args.name} existant : {server['id']} ({server['state']})")
    else:
        image = find_image(args.commercial_type)
        status, payload = call(
            "POST",
            f"{BASE}/servers",
            {
                "name": args.name,
                "project": project,
                "commercial_type": args.commercial_type,
                "image": image,
                "tags": ["ghosteo", role, authorized_key_tag()]
                + [authorized_key_tag(path) for path in args.authorized_key],
                "security_group": sg_id,
                "public_ips": [ip["id"]],
                "dynamic_ip_required": False,
                "volumes": {"0": {"size": ROOT_SIZE, "volume_type": "l_ssd"}},
            },
        )
        server = ok(status, payload, "création du serveur")["server"]
        print(f"serveur {args.name} créé : {server['id']}")
        put_user_data(server["id"], args.cloud_init)
        status, payload = call("POST", f"{BASE}/servers/{server['id']}/action", {"action": "poweron"})
        ok(status, payload, "démarrage")
        print("démarrage demandé")

    for _ in range(60):
        server = find_server(project, args.name)
        if server["state"] == "running":
            break
        time.sleep(5)
    print(f"état : {server['state']}, IP publique : {ip['address']}")

    if args.reseau_prive:
        attacher_reseau_prive(server["id"], args.reseau_prive)


if __name__ == "__main__":
    main()
