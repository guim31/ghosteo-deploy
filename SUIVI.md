# Suivi de la migration GHosteo

Journal d'avancement, tenu par l'agent. Une ligne par étape validée, datée.
Une nouvelle conversation commence par lire ce fichier.

## Phase 0 — Comptes et accès

- [x] 0.1 Compte Scaleway existant (propriétaire depuis le 30/09/2025, e-mail guilhemhenry@gmail.com) — projet `ghosteo` à confirmer (ID attendu)
- [x] 0.2 Clé d'API Scaleway `beelink-migration` rangée dans `~/.config/scw/config.yaml` (09/09/2026) ; testée : Instances et DNS répondent, IAM refusé comme voulu
- [ ] 0.3 Clé SSH du Beelink acceptée par le VPS OVH (51.178.87.41)
- [ ] 0.4 Permission Workflows accordée (temporaire)
- [ ] 0.5 Formulation HDS de remplacement reçue

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

- 09/09/2026 : une ancienne clé API Scaleway (2025, sans expiration) servait à sauvegarder
  les bases du VPS Vito vers Object Storage ; Guilhem ne sait pas si ça marche encore.
  À vérifier depuis le VPS une fois l'accès SSH ouvert (phase 0.3), avant de la supprimer.
- 09/09/2026 : la liste des buckets Object Storage répond `InvalidArgument` avec la
  nouvelle clé ; à revoir quand le projet sera confirmé (projet favori de la clé).
