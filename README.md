# ghosteo-deploy

Infrastructure et documentation de déploiement de GHosteo. Ce dépôt ne contient
**aucun secret** et aucune application : les choix, le guide et le suivi de la migration,
puis les scripts d'installation des serveurs.

- [`DECISIONS.md`](DECISIONS.md) — les choix d'architecture et pourquoi.
- [`GUIDE-PAS-A-PAS.md`](GUIDE-PAS-A-PAS.md) — le guide de migration, phase par phase.
- [`SUIVI.md`](SUIVI.md) — l'avancement.
- [`scripts/backup-vps.sh`](scripts/backup-vps.sh) — sauvegarde nocturne chiffrée des sites du VPS OVH
  vers Scaleway Object Storage, exécutée depuis le Beelink (`scripts/remote-dump.sh` est le
  morceau qui tourne côté VPS, reçu par SSH). Aucun secret dans ces fichiers.
- [`cloud-init/control.yaml`](cloud-init/control.yaml) — installation automatique du serveur de contrôle
  (SSH par clé, pare-feu, mises à jour de sécurité, Dokploy à version fixe).
- [`scripts/create-server.py`](scripts/create-server.py) — crée un serveur chez Scaleway (groupe de
  sécurité, IP fixe, machine, cloud-init) ; `scripts/scw.py` est le mini client d'API qu'il utilise.
  La clé d'API reste dans `~/.config/scw/config.yaml` sur le Beelink.
- [`compose/instance.yml`](compose/instance.yml) — gabarit d'une instance GHosteo sur Dokploy
  (web, scheduler, queue, un volume) ; `scripts/dokploy.py` est le mini client de l'API Dokploy.
