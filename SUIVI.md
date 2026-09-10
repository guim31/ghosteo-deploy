# Suivi de la migration GHosteo

Journal d'avancement, tenu par l'agent. Une ligne par étape validée, datée.
Une nouvelle conversation commence par lire ce fichier.

## Phase 0 — Comptes et accès

- [x] 0.1 Compte Scaleway existant (propriétaire depuis le 30/09/2025, e-mail guilhemhenry@gmail.com) — organisation `80540c15-2a31-4b57-ac2e-9e213936f859`, projet `ghosteo` = `a92ff601-e329-491e-87a3-4e3888a744aa`
- [x] 0.2 Clé d'API Scaleway `beelink-migration` rangée dans `~/.config/scw/config.yaml` (09/09/2026) ; testée : Instances et DNS répondent, IAM refusé comme voulu
- [x] 0.3 Clé SSH `beelink-claude` déployée sur le VPS (10/09/2026) : `ssh vito@51.178.87.41` fonctionne (pas root)
- [x] 0.4 Permission Workflows accordée le 09/09/2026 (temporaire, à retirer fin de phase 1)
- [x] 0 bis Sauvegarde nocturne des 10 sites vers Scaleway en place (10/09/2026) ; second passage complet « sans erreur » à 00:14 après correctif de droits (lecture en sudo)
- [x] 0.5 Formulation retenue par Guilhem le 09/09/2026 : « données hébergées en France, chiffrées, chez un hébergeur certifié ISO 27001 » — PR ouverte : https://github.com/guim31/ghosteoeu-main/pull/56 — **fusionnée le 10/09/2026**, à déployer depuis Vito (CGU/CGV : relecture juriste conseillée)

## Phase 1 — Image Docker

- [x] Dockerfile + docker.yml + commande `app:copy-database` : **PR ouverte** https://github.com/guim31/ghosteo/pull/192 (10/09/2026, vers `develop`) — CI verte ; réplique locale de la CI sur le NAS : Pint 288 fichiers OK, Pest 417 tests OK
- [x] Image construite sur le NAS (955 Mo) et testée le 10/09/2026 : démarrage, 64 migrations SQLite, `/up` 200, page d'installation servie, assets Vite présents, extensions gd/intl/bcmath/exif/gmp OK
- [x] Commande MySQL → SQLite testée sur le dump anonymisé de staging (10/09/2026) : 52 188 lignes / 30 tables, comptes identiques, déchiffrement OK, redémarrage sans perte (volume + hardware_id)
- [x] PR #192 fusionnée dans `develop` et PR #193 (workflow sur `main`) fusionnée ; image d'essai **`ghcr.io/guim31/ghosteo:essai-1`** publiée par Guilhem le 10/09/2026 (package privé)
- [x] Permission Workflows retirée du jeton GitHub (10/09/2026)
- [x] Formulation HDS déployée sur ghosteo.eu depuis Vito (10/09/2026)
- [x] Banc d'essai du NAS démonté (dump anonymisé supprimé, images `ghosteo:essai-*` conservées dans `/mnt/user/appdata/ghosteo-build/`)

## Phase 2 — Serveur de contrôle

Contexte utile pour démarrer (état au 10/09/2026) :
- Clé Scaleway : `~/.config/scw/config.yaml` (access/secret, org, projet `ghosteo`, fr-par-1),
  application IAM `beelink-migration` avec Instances, Block Storage, DNS et Object Storage
  sur le seul projet `ghosteo` ; pas de droit IAM ni Projets (normal).
- Prix relevés : DEV1-M (3 vCPU, 4 Go) 14,74 € HT/mois pour `control-01`.
- L'image à déployer sur staging : `ghcr.io/guim31/ghosteo:essai-1`, privée. Dokploy aura
  besoin d'un jeton GitHub classique `read:packages` saisi par Guilhem dans son UI.
- Rôles d'une instance : `web` (commande par défaut, AUTORUN migrations), `scheduler`
  (`php artisan schedule:work`, AUTORUN_ENABLED=false), `queue` (`php artisan queue:work`,
  AUTORUN_ENABLED=false) ; volume `/var/www/html/storage` ; SQLite via
  `DB_CONNECTION=sqlite`, `DB_DATABASE=/var/www/html/storage/app/database.sqlite`.
- Le gabarit de `.env` de production est dans `ghosteoeu-main`
  (`EnvFileGenerator::defaultTemplate()`) et dans `ghosteo/.env.production.example`.
- `panel.ghosteo.eu` : la zone `ghosteo.eu` reste chez OVH ; l'enregistrement A vers
  l'IP de `control-01` est à saisir par Guilhem dans l'espace client OVH (je lui dicte).
- `staging.ghosteoapp.eu` pointe aujourd'hui vers le VPS OVH via le joker ; pour tester
  staging sur Dokploy avant la phase 4, utiliser un nom hors joker (ex. `staging2`
  n'existe pas : le joker attrape tout) → un enregistrement A explicite chez OVH,
  `staging-scw.ghosteoapp.eu`, saisi par Guilhem.
- Clones de travail : `~/homelab/ghosteo-work/ghosteo` (develop) et `~/homelab/ghosteo-work/ghosteoeu-main` (main).
- Beelink : ni php, ni composer, ni accès docker ; le NAS (`ssh NASDOURY`) sert de banc d'essai Docker.


- [x] `control-01` créé chez Scaleway le 10/09/2026 : DEV1-M fr-par-1, Ubuntu 24.04, disque
  local 40 Go, **IP fixe `51.158.96.49`** (réservée à part, survit à une recréation),
  serveur `f28fa304-a7b3-4e5b-9a62-a11b0f2ea2ba`, groupe de sécurité `ghosteo-control`
  (tout refusé sauf 22/80/443 ; **3000 ouvert uniquement depuis la maison, 82.66.175.113**).
  Créé par `scripts/create-server.py control-01 DEV1-M cloud-init/control.yaml --panel-from <IP maison>`.
  Alias SSH `control-01` (root) dans `~/.ssh/config` du Beelink.
- [x] Dokploy **v0.30.6** installé par le cloud-init (Docker 28.5.0, Traefik v3.6.7, swap 2 Go,
  ufw, fail2ban, mises à jour de sécurité auto sans reboot auto). Vérifié après un
  redémarrage : services `dokploy` et `dokploy-postgres` 1/1, Traefik répond sur 80/443,
  port 3000 fermé depuis le NAS du travail (autre IP) et ouvert depuis la maison.
- [x] Enregistrements A `panel.ghosteo.eu` et `staging-scw.ghosteoapp.eu → 51.158.96.49` saisis
  par Guilhem chez OVH le 10/09/2026 ; vérifié : ghosteo.eu, demo.ghosteoapp.eu, staging et les
  instances clientes répondent toujours en 51.178.87.41 (la démo est `demo.ghosteoapp.eu`,
  pas `demo.ghosteo.eu` comme l'écrit le guide).
- [x] Panneau publié en HTTPS : **https://panel.ghosteo.eu**, certificat Let's Encrypt valide
  jusqu'au 09/12/2026, HTTP redirigé. Fait à la main dans
  `/etc/dokploy/traefik/dynamic/dokploy.yml` (le fichier que Dokploy réécrit quand on
  renseigne *Settings → Server → Domain*) ; e-mail Let's Encrypt mis à guilhemhenry@gmail.com
  dans `traefik.yml` (le défaut `test@localhost.com` est refusé par Let's Encrypt).
- [x] Compte admin Dokploy créé par Guilhem le 10/09/2026 (guilhemhenry@gmail.com), 2FA active ;
  règle 3000 du groupe de sécurité supprimée, port fermé vérifié depuis la maison.
- [x] Jeton API Dokploy rangé dans `~/.config/dokploy/token` (URL dans `url`, mode 600) ;
  client `scripts/dokploy.py`. À révoquer et recréer en fin de migration.
- [x] Registre ghcr saisi par Guilhem dans Dokploy (`ghcr.io`, `guim31`, id `R9TYou4Y3PHTOnx0e2G4K`) ;
  l'image privée `essai-1` a été tirée sans intervention.
- [x] **Staging déployé** le 10/09/2026 : projet Dokploy `ghosteo` (`LKeYTUy0wxWGmspCL908p`,
  environnement `production` `pC_5KlfCgctYLUpawSQS3`), service compose `staging`
  (`jeA57LQPy2ASqs0EXNDV1`, appName `ghosteo-staging-oygder`), gabarit `compose/instance.yml`
  (web + scheduler + queue, volume `ghosteo-staging-oygder_storage`), domaine
  **https://staging-scw.ghosteoapp.eu** (Let's Encrypt OK). Variables = `.env` du staging OVH
  adapté (SQLite dans le volume, `QUEUE_CONNECTION=database`, journaux stderr), copie de
  travail dans `/dev/shm/ghosteo/` du Beelink (tmpfs), référence dans Dokploy.
  Données : sauvegarde du 10/09 du staging OVH chargée dans un MySQL temporaire sur control-01,
  **anonymisée** (`db:anonymize`, 5 043 patients, licence neutralisée), copiée en SQLite
  (`app:copy-database --fresh`, 52 178 lignes / 30 tables), puis MySQL, dump et mots de passe
  temporaires supprimés. Documents patients non restaurés (réels). `/up` 200, migrations à jour.
- [x] Redirections et ressources en `http://` (CSS bloqué par le navigateur) : PR
  https://github.com/guim31/ghosteo/pull/194 fusionnée par Guilhem, image `essai-2` publiée,
  `TRUSTED_PROXIES=*` dans les variables du staging. Vérifié : redirections et CSS en `https://`.
- [x] Licence de recette émise par Guilhem dans ghosteo.eu (« Staging SCALEWAY », Pro, expire le
  01/01/2027), enregistrée dans l'instance le 10/09/2026 : statut `active`, `hardware_id` généré
  (`94cb7637…`) dans le volume.
- [x] **Deux redéploiements validés** le 10/09/2026 : n°1 `essai-1 → essai-2` (changement de
  `GHOSTEO_IMAGE` + `compose.redeploy`, ~60 s), n°2 même image. À chaque fois : base SQLite
  (5 034 patients), `hardware_id` et licence intacts, `/login` 200. Le cycle « nouveau tag →
  redéploiement » est donc : modifier `GHOSTEO_IMAGE` dans les variables du service, puis
  redéployer.

**✅ Phase 2 close le 10/09/2026.** Compte de recette : `utilisateur1@example.invalid` (Super
Admin, réactivé à la main le 10/09/2026 : il était `active=0` dans les données d'origine),
mot de passe commun de l'anonymisation communiqué à Guilhem dans la conversation, à changer
depuis l'application.

### Retours de la recette (après clôture)

- 10/09/2026 : **connexion OK** (Guilhem, `utilisateur2`). **Lenteurs** signalées sur
  Comptabilité → À pointer (mesuré : 80 s) et Statistiques (> 100 s, 504). Cause : **SQLite
  n'indexe pas les clés étrangères**, contrairement à InnoDB ; les `whereHas('comptabilite')`
  parcouraient toute la table. 26 index créés sur le staging → À pointer 0,4 s, Statistiques
  2,8 à 3,1 s (le reste : treize comptages par tranche d'âge, un par requête, à optimiser
  dans le code, valable aussi sous MySQL). Correctif durable : PR
  https://github.com/guim31/ghosteo/pull/195 (migration SQLite seulement, testée dans le
  conteneur). Deux index composites d'essai ajoutés à la main sur le staging
  (`comptabilites(consultation_id, visible, deleted_at)`, `consultations(patient_id, date)`),
  gain marginal, non repris dans la PR. Les pics à 13 s observés pendant l'analyse venaient
  de mes propres tests concurrents (verrou d'écriture WAL), pas de l'application.
  **Point de vigilance pour la décision SQLite** (DECISIONS § 7.3) : validé pour le volume
  d'un cabinet, à condition que cette migration soit dans l'image déployée.

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

- 10/09/2026 : **clé SSH sur les images Scaleway** — la section `users:` du cloud-init n'a
  pas donné accès à root : l'agent Scaleway (`scw-fetch-ssh-keys`) **régénère
  `/root/.ssh/authorized_keys` à chaque démarrage** depuis les clés IAM du projet et les
  tags `AUTHORIZED_KEY=<clé, espaces → _>` du serveur. La clé `beelink-migration` n'a pas le
  droit d'écrire des clés IAM, donc `create-server.py` passe la clé publique du Beelink en
  tag. Diagnostic sans SSH : Traefik sur 80/443 et Dokploy sur 3000 répondaient, donc le
  cloud-init avait bien tourné ; un redémarrage après pose du tag a suffi.
- 10/09/2026 : **Dokploy, ce qu'il faut savoir** — l'API est `POST /api/<routeur>.<action>`
  avec l'en-tête `x-api-key`, spec complète sur `/api/settings.getOpenApiDocument` ; un service
  compose reçoit un suffixe aléatoire d'appName ; Dokploy dépose le compose et le `.env` dans
  `/etc/dokploy/compose/<appName>/code/` et injecte lui-même les étiquettes Traefik du domaine
  (service `web`, port 8080) ; le `docker login` ghcr est fait par Dokploy, l'hôte n'a pas
  d'identifiant de registre mais garde l'image en cache local (utile pour un `docker run`
  ponctuel : anonymisation, copie). Scaleway bloque le SMTP sortant (25/465/587) par défaut :
  sans effet, Mailgun passe en HTTPS.
- 10/09/2026 : le Beelink n'a ni `scw` ni `jq` ; `scripts/scw.py` (bibliothèque standard
  Python) sert de client d'API. Le DEV1-M coûte 0,0202 € HT/h ; l'IP fixe routée est
  facturée en plus, quelques euros par mois.

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
  Vérifié le 10/09 : le mécanisme était mort (voir ci-dessus).
- 09/09/2026 : l'ancienne clé API Scaleway de 2025 a été supprimée par Guilhem le 09/09 au soir.
