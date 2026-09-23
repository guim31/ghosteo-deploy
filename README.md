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
  (SSH par clé, pare-feu, mises à jour de sécurité, Dokploy à version fixe) ;
  [`cloud-init/worker.yaml`](cloud-init/worker.yaml) — la même base pour un serveur de clients, sans
  Docker ni Dokploy (le panneau les installe en attachant le serveur).
- [`scripts/create-server.py`](scripts/create-server.py) — crée un serveur chez Scaleway (groupe de
  sécurité, IP fixe, machine, cloud-init) ; `scripts/scw.py` est le mini client d'API qu'il utilise.
  La clé d'API reste dans `~/.config/scw/config.yaml` sur le Beelink. Il imprime en fin de course
  les étapes qui suivent l'attachement à Dokploy.
- [`scripts/activer-metriques.py`](scripts/activer-metriques.py) — **active l'agent de métriques
  Dokploy** d'un serveur (même configuration que worker-01), vérifie que le back-office le lit par
  le réseau privé et imprime l'adresse à saisir dans Réglages → Serveurs. `--verifier` ne fait que
  lire. À lancer pour **chaque nouveau serveur** : worker-02 était resté sans relevé faute de ce geste.
- [`scripts/archive-vps.sh`](scripts/archive-vps.sh) — **archive finale** du VPS OVH avant sa
  résiliation, dans un dépôt à part et **sans rétention** : la sauvegarde nocturne purge à
  30 jours, une archive définitive posée à côté d'elle disparaîtrait donc toute seule.
- [`scripts/backup-scaleway.sh`](scripts/backup-scaleway.sh) — sauvegarde nocturne du **nouvel**
  hébergement : les instances de worker-01 (base SQLite copiée par `VACUUM INTO`, car le mode WAL
  rend une copie de fichier à chaud inexploitable), le back-office de control-01 et la base du
  panneau Dokploy. `scripts/remote-dump-scaleway.sh` est le morceau qui tourne côté serveur.
  Le Beelink tire et chiffre avant l'envoi ; les serveurs ne détiennent aucun identifiant.
- [`scripts/backoffice-suivre-main.py`](scripts/backoffice-suivre-main.py) — **ghosteo.eu suit `main`
  du back-office** : chaque fusion est mise en ligne dans les cinq minutes, avec copie de la base
  avant, vérification réelle et retour automatique à l'image précédente. `--tag main-abc1234` met en
  ligne une image précise, `--etat` montre où on en est. Cron du Beelink décalé de deux minutes par
  rapport à celui de la recette.
- [`scripts/recette-suivre-develop.py`](scripts/recette-suivre-develop.py) — la recette
  `staging.ghosteoapp.eu` suit l'image `:develop`, construite à chaque fusion. Cron du Beelink
  toutes les 5 minutes. Il **tire avant de redéployer** : le tag est mouvant, et `docker compose
  up -d` ne retire pas une image déjà en cache — redéployer sans tirer ne ferait rien.
- [`scripts/migrate-backoffice.py`](scripts/migrate-backoffice.py) — bascule de `ghosteo.eu`
  lui-même, qui n'est pas une instance cliente : base MySQL conservée, zone DNS chez OVH donc
  changement d'adresses à la main, et mise en sommeil du planificateur de la copie tant que
  l'ancien back-office tourne — deux ordonnanceurs ne doivent jamais coexister.
- [`scripts/migrate-instance.py`](scripts/migrate-instance.py) — migration d'une instance cliente du
  VPS OVH vers un worker Dokploy, en quatre commandes (`ttl`, `preparer`, `basculer`, `verifier`).
  La clé de chiffrement de l'instance est conservée, sans quoi les dossiers patients seraient
  illisibles : c'est pourquoi l'assistant du back-office, qui en tire une neuve, ne convient pas.
  L'inventaire des cabinets se met dans `clients.yaml` (non versionné, voir `clients.yaml.exemple`).
- [`compose/instance.yml`](compose/instance.yml) — gabarit d'une instance GHosteo sur Dokploy
  (web, scheduler, queue, un volume) ; `scripts/dokploy.py` est le mini client de l'API Dokploy.
- [`scripts/dns-scaleway.py`](scripts/dns-scaleway.py) — recopie l'export de zone OVH (`dns/`) chez Scaleway
  Domains & DNS, compare les réponses des deux annuaires, et pose les enregistrements A des
  bascules d'instances (`set <nom> <ip> [ttl]`). Les vérifications se lancent depuis `control-01` :
  le résolveur de la maison intercepte les requêtes DNS sortantes.
