#!/usr/bin/env python3
"""Mini client de l'API Dokploy (panneau GHosteo), bibliothèque standard seulement.

Jeton dans ~/.config/dokploy/token, URL du panneau dans ~/.config/dokploy/url
(jamais dans ce dépôt).

Usage :
  dokploy.py GET  compose.one composeId=<id>
  dokploy.py POST compose.deploy '{"composeId": "<id>"}'
  dokploy.py POST compose.saveEnvironment @fichier.json     (corps lu dans un fichier)
Le résultat est imprimé en JSON ; un code HTTP hors 2xx sort en 1.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

CONF = os.path.expanduser("~/.config/dokploy")


def call(method, route, body=None, query=None):
    token = open(os.path.join(CONF, "token")).read().strip()
    base = open(os.path.join(CONF, "url")).read().strip()
    url = f"{base}/api/{route}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"x-api-key": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
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
    method, route = sys.argv[1].upper(), sys.argv[2]
    body, query = None, {}
    if method == "GET":
        for arg in sys.argv[3:]:
            k, v = arg.split("=", 1)
            query[k] = v
    elif len(sys.argv) > 3:
        raw = sys.argv[3]
        body = json.load(open(raw[1:])) if raw.startswith("@") else json.loads(raw)
    status, payload = call(method, route, body, query)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    sys.exit(0 if 200 <= status < 300 else 1)


if __name__ == "__main__":
    main()
