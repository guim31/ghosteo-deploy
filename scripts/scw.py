#!/usr/bin/env python3
"""Mini client de l'API Scaleway, sans dépendance hors bibliothèque standard.

Lit la clé dans ~/.config/scw/config.yaml (jamais dans ce dépôt).

Usage :
  scw.py GET  /instance/v1/zones/fr-par-1/servers
  scw.py POST /instance/v1/zones/fr-par-1/servers '{"name": "..."}'
  scw.py DELETE /instance/v1/zones/fr-par-1/servers/<id>
Un chemin relatif (sans / initial) est préfixé par https://api.scaleway.com/.
Le résultat est imprimé en JSON indenté ; les erreurs HTTP sortent en code 1.
"""
import json
import os
import sys
import urllib.error
import urllib.request

CONFIG = os.path.expanduser("~/.config/scw/config.yaml")
API = "https://api.scaleway.com"


def load_config():
    cfg = {}
    with open(CONFIG) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            cfg[key.strip()] = value.strip()
    return cfg


def call(method, path, body=None, raw=False):
    cfg = load_config()
    url = path if path.startswith("http") else API + ("/" + path.lstrip("/"))
    data = None
    headers = {"X-Auth-Token": cfg["secret_key"]}
    if body is not None:
        data = json.dumps(body).encode() if not raw else body.encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode()
            return resp.status, (json.loads(text) if text else None)
    except urllib.error.HTTPError as err:
        text = err.read().decode()
        try:
            return err.code, json.loads(text)
        except json.JSONDecodeError:
            return err.code, {"raw": text}


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    method, path = sys.argv[1].upper(), sys.argv[2]
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    status, payload = call(method, path, body)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    sys.exit(0 if 200 <= status < 300 else 1)


if __name__ == "__main__":
    main()
