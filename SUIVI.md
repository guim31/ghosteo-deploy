# Suivi de la migration GHosteo

Journal d'avancement, tenu par l'agent. Une ligne par étape validée, datée.
Une nouvelle conversation commence par lire ce fichier.

## Phase 0 — Comptes et accès

- [x] 0.1 Compte Scaleway existant (propriétaire depuis le 30/09/2025, e-mail guilhemhenry@gmail.com) — organisation `80540c15-2a31-4b57-ac2e-9e213936f859`, projet `ghosteo` = `a92ff601-e329-491e-87a3-4e3888a744aa`
- [x] 0.2 Clé d'API Scaleway `beelink-migration` rangée dans `~/.config/scw/config.yaml` (09/09/2026) ; testée : Instances et DNS répondent, IAM refusé comme voulu
- [x] 0.3 Clé SSH `beelink-claude` déployée sur le VPS (10/09/2026) : `ssh vito@51.178.87.41` fonctionne (pas root)
- [x] 0.4 Permission Workflows accordée le 09/09/2026 (temporaire, à retirer fin de phase 1)
- [x] 0 bis Sauvegarde nocturne des 10 sites vers Scaleway en place (10/09/2026)
- [x] 0.5 Formulation retenue par Guilhem le 09/09/2026 : « données hébergées en France, chiffrées, chez un hébergeur certifié ISO 27001 » — PR ouverte : https://github.com/guim31/ghosteoeu-main/pull/56 — **fusionnée le 10/09/2026**, à déployer depuis Vito (CGU/CGV : relecture juriste conseillée)

## Phase 1 — Image Docker

- [ ] Dockerfile + docker.yml en PR sur `ghosteo`
- [ ] Image testée (démarrage, installation, sauvegarde/restauration, hardware_id)
- [ ] Commande MySQL → SQLite écrite et testée sur données anonymisées
- [ ] Tag de test posé, image présente sur ghcr (privée)
- [ ] Permission Workflows retirée

## Phase 2 — Serveur de contrôle

- [ ] `control-01` créé chez Scaleway
- [ ] Dokploy installé, compte admin créé par Guilhem, 2FA
- [ ] Jeton API Dokploy rangé sur le Beelink
- [ ] Registre ghcr saisi dans Dokploy
- [ ] Staging déployé depuis l'image, deux redéploiements validés

## Phase 3 — Back-office

- [ ] PR `ghosteoeu-main` (serveurs, DokployClient, étapes, DNS) fusionnée
- [ ] Réglages Dokploy saisis dans l'admin
- [ ] Client fictif déployé puis supprimé trois fois

## Phase 4 — DNS, worker, démo

- [ ] Zone `ghosteoapp.eu` recopiée chez Scaleway et vérifiée
- [ ] Serveurs DNS changés chez OVH, propagation constatée
- [ ] `worker-01` créé et attaché
- [ ] Démo migrée

## Phase 5 — Clients

| Client | Créneau | Migré le | Vérifié par le client | Ancienne instance éteinte le |
|---|---|---|---|---|
| (cabinet de Guilhem) | | | | |

## Phase 6 — Fin

- [ ] ghosteo.eu basculé
- [ ] Sauvegarde finale de l'ancien serveur sur Object Storage
- [ ] VPS OVH résilié
- [ ] Clés Scaleway et Dokploy révoquées et recréées

## Notes

- 10/09/2026 : inventaire du VPS OVH (vps-fdce4053, 6 vCPU, 11 Go, 96 Go disque à 44 %,
  PHP 8.4, MySQL 8.4, Node 22). Utilisateurs isolés = un par site : alexiagauthier,
  anaisdelaunay, aurelienmariejoseph, cabinet-blachon-thivillier, cedricrousseau,
  guilhemhenry, xavierpages (7 instances clientes, Guilhem compris), ghosteoeudemo,
  ghosteoserver (ghosteo.eu), staging. Les sauvegardes locales `database_backups` datent
  de mars 2026 ; script `upload_backups_to_scaleway.sh` (rclone vers le bucket
  `backup-vps-guilhemhenry-2023`) : **mort** — aucune config rclone pour `vito`, aucun cron,
  `/home/DB_BACKUPS` vide, aucun dump de moins de 7 jours lisible. Reste à vérifier la
  page Backups de Vito (sauvegardes envoyées directement à un Storage Provider), que
  seul le panneau montre. Confirmé le 09/09/2026 par capture : les 6 sauvegardes Vito sont
  en **échec** depuis octobre 2025 et ne couvraient que 3 clients sur 7.
- 10/09/2026 : **sauvegarde nocturne mise en place** (phase 0 bis). `scripts/backup-vps.sh`
  tourne sur le Beelink à 02:30 (cron), tire dump MySQL + `storage/app` + `.env` de chacun
  des 10 sites, chiffre en AES-256 (gpg, passphrase dans `~/.config/ghosteo-backup/passphrase`,
  à copier dans le gestionnaire de mots de passe de Guilhem) et dépose dans le bucket
  `ghosteo-backups-vps` (fr-par, projet ghosteo). Rétention 30 jours. Journal :
  `~/ghosteo-backup.log`. Test de restauration réussi sur cedric-rousseau (38 tables).

- 09/09/2026 : prix Scaleway relevés par l'API (fr-par-1, HT/mois) : DEV1-M 3 vCPU 4 Go
  14,74 € (serveur de contrôle) ; DEV1-L 4 vCPU 8 Go 31,27 € (worker). Total attendu ≈ 46 €.

- 09/09/2026 : une ancienne clé API Scaleway (2025, sans expiration) servait à sauvegarder
  les bases du VPS Vito vers Object Storage ; Guilhem ne sait pas si ça marche encore.
  À vérifier depuis le VPS une fois l'accès SSH ouvert (phase 0.3), avant de la supprimer.
- 09/09/2026 : la liste des buckets Object Storage répond `InvalidArgument` avec la
  nouvelle clé ; à revoir quand le projet sera confirmé (projet favori de la clé).
