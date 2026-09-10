#!/usr/bin/env python3
"""Zone ghosteoapp.eu chez Scaleway Domains & DNS : recopie et comparaison.

  dns-scaleway.py push    dns/<fichier>.zone      recopie le fichier de zone OVH chez Scaleway
  dns-scaleway.py compare dns/<fichier>.zone      interroge OVH et Scaleway et compare
  dns-scaleway.py status                          état de validation du domaine externe
  dns-scaleway.py records                         liste les enregistrements de la zone Scaleway

Le fichier de zone est l'export « mode textuel » d'OVH. Les lignes SOA et NS sont ignorées
(propres à l'hébergeur). Une ligne dont le nom est vide hérite du nom précédent (« @ »).
Aucun secret : la clé d'API est lue par scw.py dans ~/.config/scw/config.yaml.
"""
import os
import random
import string
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scw import call, load_config  # noqa: E402

ZONE = "ghosteoapp.eu"
OVH_NS = "dns10.ovh.net"
SCW_NS = ("ns0.dom.scw.cloud", "ns1.dom.scw.cloud")
SKIP = {"SOA", "NS"}


def parse_zone(path):
    """Rend une liste de (nom, ttl, type, données) ; nom « @ » pour la racine."""
    records, owner, default_ttl = [], "@", 3600
    for raw in open(path, encoding="utf-8"):
        line = raw.split(";", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("$TTL"):
            default_ttl = int(line.split()[1])
            continue
        if line[0] not in " \t":
            owner = line.split()[0]
        parts = line.split()
        if line[0] not in " \t":
            parts = parts[1:]
        if parts and parts[0].isdigit():
            ttl, parts = int(parts[0]), parts[1:]
        else:
            ttl = default_ttl
        if parts and parts[0] == "IN":
            parts = parts[1:]
        rtype, data = parts[0], " ".join(parts[1:])
        if rtype in SKIP:
            continue
        records.append((owner, ttl, rtype, data))
    return records


def to_scaleway(owner, ttl, rtype, data):
    name = "" if owner == "@" else owner
    rec = {"name": name, "type": rtype, "ttl": ttl}
    if rtype == "MX":
        prio, target = data.split(None, 1)
        rec["priority"] = int(prio)
        rec["data"] = target
    elif rtype == "TXT":
        rec["data"] = data.strip('"')
    else:
        rec["data"] = data
    return rec


def push(path):
    records = [to_scaleway(*r) for r in parse_zone(path)]
    print(f"{len(records)} enregistrements lus dans {path} (hors SOA/NS)")
    # Un « set » par (nom, type) : rejouable, remplace ce qui existe.
    groups = {}
    for rec in records:
        groups.setdefault((rec["name"], rec["type"]), []).append(rec)
    changes = [
        {"set": {"id_fields": {"name": n, "type": t}, "records": recs}}
        for (n, t), recs in groups.items()
    ]
    status, payload = call(
        "PATCH", f"/domain/v2beta1/dns-zones/{ZONE}/records",
        {"changes": changes, "return_all_records": True},
    )
    if not 200 <= status < 300:
        print("ERREUR HTTP", status, payload, file=sys.stderr)
        sys.exit(1)
    print("recopié. Zone Scaleway maintenant :")
    for rec in payload.get("records", []):
        print(f"  {rec['name'] or '@':<20} {rec['ttl']:>5} {rec['type']:<6} {rec.get('priority', '') or ''} {rec['data']}")


def dig(name, rtype, server):
    out = subprocess.run(
        ["dig", "+short", "+norecurse", "+time=5", "+tries=2", rtype, name, f"@{server}"],
        capture_output=True, text=True,
    ).stdout
    return sorted(line.strip().lower() for line in out.splitlines() if line.strip())


def compare(path):
    fqdn = lambda owner: ZONE if owner == "@" else f"{owner}.{ZONE}"
    queries = sorted({(fqdn(o), t) for o, _, t, _ in parse_zone(path)})
    # Le joker : trois noms au hasard, qui n'existent nulle part.
    for _ in range(3):
        label = "".join(random.choices(string.ascii_lowercase, k=8))
        queries.append((f"{label}.{ZONE}", "A"))
    ok = True
    for name, rtype in queries:
        ovh = dig(name, rtype, OVH_NS)
        scw = [dig(name, rtype, ns) for ns in SCW_NS]
        same = ovh == scw[0] == scw[1]
        ok &= same
        mark = "OK " if same else "DIFF"
        print(f"{mark} {rtype:<5} {name:<40} OVH={ovh} SCW={scw[0]}" + ("" if scw[0] == scw[1] else f" ns1={scw[1]}"))
    print("\nIDENTIQUES" if ok else "\nDIFFÉRENCES : ne pas changer les serveurs DNS")
    sys.exit(0 if ok else 1)


def status():
    st, payload = call("GET", f"/domain/v2beta1/domains/{ZONE}")
    print("domaine :", payload.get("status"), "| jeton :",
          (payload.get("external_domain_registration_status") or {}).get("validation_token"))
    st, payload = call("GET", f"/domain/v2beta1/dns-zones?project_id={load_config()['default_project_id']}")
    for z in payload.get("dns_zones", []):
        print("zone :", z["domain"], z.get("subdomain") or "", "|", z["status"], "| ns :", z.get("ns"))
    if not payload.get("dns_zones"):
        print("zone : (aucune pour l'instant)")


def records():
    st, payload = call("GET", f"/domain/v2beta1/dns-zones/{ZONE}/records?page_size=100")
    if st != 200:
        print(payload); sys.exit(1)
    for rec in payload["records"]:
        print(f"  {rec['name'] or '@':<20} {rec['ttl']:>5} {rec['type']:<6} {rec.get('priority', '') or ''} {rec['data']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "push" and len(sys.argv) == 3:
        push(sys.argv[2])
    elif cmd == "compare" and len(sys.argv) == 3:
        compare(sys.argv[2])
    elif cmd == "status":
        status()
    elif cmd == "records":
        records()
    else:
        print(__doc__); sys.exit(2)
