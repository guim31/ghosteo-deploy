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

Contexte utile (état au 10/09/2026) :
- Banc de test du NAS pour `ghosteoeu-main` : `/mnt/user/appdata/ghosteoeu-ci/src` (rsync depuis le
  clone, sans `vendor`/`node_modules`/`public/build`), image `ghosteoeu-ci:php` (serversideup 8.3-cli
  + bcmath/intl/gd), assets construits une fois avec `node:20-alpine`. Commande :
  `docker run --rm --user root -v …/src:/app -w /app ghosteoeu-ci:php sh -c "vendor/bin/pint --test; php artisan test --compact; vendor/bin/phpstan analyse"`.
  Sans assets, 32 tests échouent sur « Vite manifest not found » : ce n'est pas le code.
- Identifiants Dokploy à saisir dans l'admin : URL `https://panel.ghosteo.eu`, environnement
  `pC_5KlfCgctYLUpawSQS3` (projet `ghosteo`), image par défaut `ghcr.io/guim31/ghosteo:essai-2`
  tant qu'aucune version taguée n'existe ; serveur `control-01` = machine du panneau
  (identifiant vide), IP `51.158.96.49`.
- Le mode DNS reste « manuel » jusqu'à la phase 4 : l'assistant vérifie et attend ; le client
  fictif `test-migration.ghosteoapp.eu` demande donc un enregistrement A chez OVH (Guilhem).

- [x] **PR ouverte** le 10/09/2026 : https://github.com/guim31/ghosteoeu-main/pull/57 — serveurs,
  `DokployClient`, moteurs `VitoBackend`/`DokployBackend` derrière `DeploymentBackend`, étape DNS
  (manuel / Scaleway), gabarits .env et compose, réglages. Pint, PHPStan, 409 tests verts sur le NAS.
- [x] PR #57 fusionnée (squash) et ghosteo.eu redéployé depuis Vito par Guilhem le 10/09/2026 ;
  migrations jouées (tables `servers`, colonnes `backend`…).
- [x] Réglages Dokploy : URL + jeton saisis par Guilhem ; environnement `pC_5KlfCgctYLUpawSQS3`,
  image par défaut `ghcr.io/guim31/ghosteo:essai-2` et mode DNS « manuel » posés par tinker
  (`sudo -u ghosteoserver php artisan tinker --execute`, l'utilisateur `vito` a sudo). Le
  panneau répond v0.30.6 depuis le back-office.
- [x] Serveur `control-01` déclaré (#1, Dokploy, machine du panneau, 51.158.96.49, plafond 3).
- [x] **Client fictif `test-migration.ghosteoapp.eu` déployé puis supprimé trois fois** le
  10/09/2026 (enregistrement A saisi par Guilhem chez OVH). Les trois passages : succès de bout
  en bout (DNS → application → variables → domaine → déploiement → conteneurs → HTTPS 200 →
  fin), ~8 min chacun au rythme du planificateur (une étape par minute), sans licence donc sans
  inscription au moniteur. Suppression : `compose.delete` (volumes compris) + lignes du
  back-office ; zéro conteneur, zéro volume restant. Scripts jetables dans `/tmp` du Beelink.
- [x] **PR #58 fusionnée** et déployée par Guilhem le 10/09/2026 : cascade de mise à jour des
  instances Dokploy (image cible, remplacement de `GHOSTEO_IMAGE`, `compose.redeploy`, suivi).
- [x] **Cascade testée en réel sur le staging** (instance #10 rattachée à control-01 et à son
  compose) : `essai-2 → essai-1` en 1 min, puis retour `essai-1 → essai-2` en 1 min ; à chaque
  fois 5 034 patients, `hardware_id` et licence intacts, ressources en HTTPS après le retour.
  Le retour arrière est bien « la même cascade avec le tag précédent ».

**✅ Phase 3 close le 10/09/2026.** Depuis l'admin de ghosteo.eu : un clic crée une instance
sur Scaleway (DNS à poser à la main jusqu'à la phase 4), un clic la met à jour.


## Phase 4 — DNS, worker, démo

Contexte utile (état au 10/09/2026) :
- Export de la zone OVH : `dns/ghosteoapp.eu.ovh-2026-09-10.zone` (16 lignes). À recopier chez
  Scaleway **sauf** SOA et NS (propres à OVH). Le joker `*` et `@` restent vers `51.178.87.41`
  tant que les clients ne sont pas migrés. `panel` (ghosteoapp.eu) pointe vers l'ancien VPS :
  c'est un vestige, sans rapport avec `panel.ghosteo.eu`. Les MX/SPF servent au courrier OVH du
  domaine : à conserver à l'identique.
- Le changement de serveurs DNS (`ns0.dom.scw.cloud`, `ns1.dom.scw.cloud`) est le geste de
  Guilhem, une fois la copie vérifiée. Ensuite : passer `dns_provider` à `scaleway` dans les
  réglages de ghosteo.eu et y saisir un jeton Scaleway DNS (ou réutiliser la clé du Beelink ?
  non : une clé dédiée, périmètre DNS seulement).

- [~] 10/09/2026 : `ghosteoapp.eu` déclaré chez Scaleway comme **domaine externe** (statut
  `checking`). Scaleway ne crée la zone qu'après une preuve de propriété : un TXT
  `_scaleway-challenge.ghosteoapp.eu` = `d97bbb2a-6689-4092-9094-da451f56d4b1` à poser chez OVH
  (Guilhem). Le guide ne prévoyait pas cette étape. Une fois le domaine `active`, la zone se
  recopie et se vérifie avec `scripts/dns-scaleway.py push|compare dns/…zone` (SOA/NS exclus,
  MX avec priorité, joker `*` compris). Ce TXT peut être retiré d'OVH après validation.
- [x] **Zone `ghosteoapp.eu` recopiée chez Scaleway et vérifiée** le 10/09/2026 : TXT posé par
  Guilhem, domaine `active` en ~20 min, 13 enregistrements recopiés (`dns-scaleway.py push`),
  zone `active` sur `ns0`/`ns1.dom.scw.cloud`. Comparaison depuis control-01 : les 13 lignes et
  trois noms au hasard (joker) répondent à l'identique chez OVH et Scaleway. **Piège** : depuis
  le Beelink, toute requête DNS vers un serveur externe est interceptée par le résolveur de la
  maison (réponses non autoritaires, REFUSED sans récursion) — les vérifications DNS se font
  depuis control-01. Le TXT `_scaleway-challenge` peut maintenant être retiré chez OVH.
- [~] Serveurs DNS changés chez OVH par Guilhem le 10/09/2026 vers 15h20 (`ns0`/`ns1.dom.scw.cloud`,
  sans IP associée ; OVH affiche « en cours d'activation »). Propagation surveillée depuis control-01
  (registre `.eu` via `x.dns.eu`, Cloudflare, Google).
  **11/09/2026 11h15 : toujours OVH au registre `.eu`.** Cause : le domaine avait **DNSSEC activé
  chez OVH**. OVH a retiré la signature (DS) au registre à 15h17 le 10/09, puis retarde le changement
  de serveurs de 24 h pour laisser expirer les caches (exécution planifiée le 11/09 à 15h17, visible
  dans « Opérations en cours », avec une option « skip » **à ne pas utiliser** : un résolveur qui a
  encore l'ancien DS en cache refuserait les réponses non signées de Scaleway). À prévoir aussi pour
  `ghosteo.eu` en phase 6 : désactiver DNSSEC la veille, ou compter 24 h de plus.
- [x] **Propagation constatée le 11/09/2026** : OVH a exécuté l'opération à 15h17 ; à 15h19 le
  registre `.eu` délègue à `ns0`/`ns1.dom.scw.cloud`, Google, Quad9 puis Cloudflare répondent par
  Scaleway (alternance de caches pendant l'heure suivante, normale). Par le nouveau chemin : apex,
  démo, staging, instances clientes → `51.178.87.41`, `staging-scw` → `51.158.96.49`, MX intacts,
  démo en HTTPS 302. Aucun client touché. Reste à faire côté OVH par Guilhem, sans urgence :
  retirer le TXT `_scaleway-challenge` (dans la zone OVH, désormais inactive).
- [x] **`worker-01` créé et attaché** le 11/09/2026 : Scaleway DEV1-L fr-par-1 (4 vCPU, 8 Go,
  31,27 € HT/mois), **IP fixe `51.15.247.226`**, serveur `62f5777e-6d5a-43c4-9e35-085d307c8de5`,
  groupe de sécurité `ghosteo-worker` (**22 ouvert seulement depuis control-01 et la maison**,
  80/443 publics). Cloud-init `worker.yaml` appliqué en 250 s (swap 2 Go, ufw, fail2ban, MAJ de
  sécurité), sans Docker : c'est le panneau qui l'installe.
  Attaché à Dokploy : clé SSH dédiée `ghosteo-workers` (`-jg8rdKLAHDliUS2mJsQe`, générée par le
  panneau, posée en tag AUTHORIZED_KEY par `create-server.py --authorized-key`), serveur
  `zHNG7citX1VozvviOoNga`, `server.setup` ~10 min (Docker 28.5.0, swarm, dokploy-network,
  Traefik 3.6.25, rclone/nixpacks/pack/railpack), `server.validate` : tout à `enabled`.
  **Adresse Let's Encrypt corrigée** dans `/etc/dokploy/traefik/traefik.yml`
  (`test@localhost.com` → guilhemhenry@gmail.com, sauvegarde `.bak-20260911`, Traefik redémarré)
  — même piège que control-01, `server.setup` ne le fait pas.
  Déclaré dans le back-office : serveur **#2**, plafond 12, `provider=scaleway`, `external_id` =
  l'identifiant Dokploy. Alias SSH `worker-01` dans `~/.ssh/config` du Beelink.
  **Piège de méthode** : `pgrep -f "Installing requirements"` lancé par SSH s'attrape lui-même
  (la chaîne est dans sa propre ligne de commande) — la surveillance annonçait « en cours » alors
  que l'installation était finie. Vérifier par `server.validate`, pas par `pgrep`.
- [x] **Démo migrée** le 11/09/2026, de 15h48 à 16h26 (coupure HTTPS réelle : ~12 min, de la bascule
  DNS à 16h13 au certificat à 16h25). `demo.ghosteoapp.eu` tourne sur worker-01 : service compose
  `MCvTGAWk5Fa6E4Nz2RQ5Y` (appName `ghosteo-demo-fotozg`), volume `ghosteo-demo-fotozg_storage`,
  certificat Let's Encrypt jusqu'au 10/12/2026, HTTP redirigé, ressources en HTTPS.
  Contrôles après bascule : 71 patients, 747 consultations, 2 comptes — identiques à l'ancienne —,
  déchiffrement OK (clé d'origine conservée), `hardware_id` conservé, aucune migration en attente,
  `/up` 200, `/login` 200. Instance #2 du back-office rattachée au serveur #2.
  **L'ancienne instance n'a pas été mise en maintenance** (action refusée par le contrôle
  d'autorisations de l'agent) : pour la démo c'est sans conséquence, mais **pour un vrai client il
  faut cette étape** — prévoir une règle d'autorisation ou que Guilhem lance `php artisan down`
  lui-même au début du créneau. L'ancienne démo tourne toujours, intacte, sur le VPS OVH.
  Sauvegardes conservées dans `/root/demo-migration/` de control-01 (dump à froid, SQLite, `.env`
  d'origine, mode 600) — à supprimer après 30 jours.

### Ce que la répétition générale a appris (à appliquer en phase 5)

1. **L'assistant du back-office n'est pas l'outil de migration.** Il tire une nouvelle `APP_KEY` à
   chaque déploiement (`EnvFileGenerator`, aucun champ pour en fournir une), ce qui rendrait
   illisibles les dossiers patients d'une instance migrée. Une migration se fait donc par appels
   directs à Dokploy, en repartant du `.env` de l'ancienne instance. *Amélioration possible du
   back-office : un mode « migration » avec un champ APP_KEY.*
2. **Ordre retenu, qui réduit la coupure à quelques minutes** : créer l'instance sur le worker et
   la déployer **avant** de toucher au DNS (le certificat échouera, c'est normal), puis maintenance,
   sauvegarde à froid, conversion, copie dans le volume, **et seulement alors** la bascule DNS.
   Tout ce qui est long (téléchargement de l'image, démarrage, migrations) est ainsi fait à froid.
3. **Abaisser le TTL avant la bascule.** `dns-scaleway.py set <nom> <ancienne IP> 60` la veille :
   sans ça, l'ancienne réponse reste en cache jusqu'à 1 h. Avec un TTL de 60 s, Google et
   Cloudflare ont suivi en moins d'une minute.
4. **Traefik ne retente pas indéfiniment un certificat en échec.** Les tentatives d'avant la
   bascule échouent (le défi ACME part vers l'ancien serveur), puis il s'arrête. Après la bascule
   DNS, **redémarrer `dokploy-traefik` sur le worker** : le certificat est délivré en ~30 s.
   Sans ce geste, le site reste sur le certificat par défaut de Traefik, avec alerte du navigateur.
5. **Un worker neuf ne sait pas tirer les images privées.** Le premier déploiement échoue sur
   `unauthorized`. Il faut lancer une fois le test du registre **en visant ce serveur**
   (`registry.testRegistryById` avec le `serverId`, ou le bouton de test dans Dokploy) : il pose
   `/root/.docker/config.json` sur la machine. À faire pour chaque nouveau worker.
   *Correction à DECISIONS § 2* : les workers **stockent bien** un identifiant de registre (le
   jeton `read:packages`), contrairement à ce qui y était supposé.
6. **Vérifier depuis control-01, jamais depuis le Beelink.** Le résolveur de la maison garde
   l'ancienne adresse en cache : une vérification faite d'ici a « validé » l'ancien serveur, avec
   son ancien certificat. Même piège que pour la comparaison des zones.
7. **`hardware_id` vit dans `storage/app/`.** Extraire l'archive de `storage` **sans**
   `--strip-components` (le volume est monté sur `storage`, pas sur `storage/app`), sinon la
   licence repart sur une nouvelle empreinte matérielle.
8. **Poser un enregistrement change aussi le TTL du joker.** Chez Scaleway, un `set` désignant un
   enregistrement par son nom et son type (ce que fait `ScalewayDnsProvider` du back-office)
   réécrit au passage le TTL de `*`. Reproduit trois fois. Sans gravité — l'adresse du joker n'est
   pas touchée, seule sa durée de cache l'est — mais à savoir avant de s'en inquiéter. Pour viser
   un enregistrement sans ambiguïté, le désigner par son `id` (`{"set": {"id": "...", ...}}`).
9. **MySQL temporaire de conversion** : `mysql:8.4` refuse `--default-authentication-plugin`
   (option supprimée) et n'accepte `root` **que par TCP** (`--protocol=TCP -h127.0.0.1`), pas par
   socket. Attendre par `mysqladmin ping` en boucle, pas sur le message « ready for connections »
   du journal, qui est celui du serveur temporaire d'initialisation.

### Dimensionnement revu le 11/09/2026

Mesure sur la démo en service : **une instance complète occupe ~140 Mo** (web 64, scheduler 48,
queue 49), pas les 250 à 400 Mo estimés dans DECISIONS § 4 — cette estimation supposait un
conteneur MariaDB par client, supprimé par le choix SQLite. PHP-FPM est en mode `ondemand`
(20 enfants au plus, 256 Mo chacun) : une instance au repos ne coûte presque rien.

**worker-01 ramené de DEV1-L à DEV1-M** (3 vCPU, 4 Go) le 11/09/2026 à la demande de Guilhem :
31,27 → 14,74 € HT/mois. Coupure de 2 min 20 (extinction, changement d'offre par l'API, rallumage ;
les conteneurs repartent seuls). Le disque local de 40 Go posé par `create-server.py` rend ce
changement possible sans recréer la machine — un DEV1-L par défaut aurait pris 80 Go et bloqué le
retour en arrière. Après réduction : 699 Mo utilisés sur 3 909, dont 119 Mo pour Traefik.
Plafond laissé à 12 ; à revoir vers 8-10 si les instances réelles s'avèrent plus lourdes que la démo.

**Coût réel de l'ancien hébergement, relevé sur la facture OVH FR72635076 du 23/09/2025** :
VPS-2 (`vps-fdce4053`, 6 vCPU, 12 Go, 100 Go) **71,40 € HT pour 12 mois**, plus l'option Snapshot
8,40 € HT/an, l'option Automated Backup offerte : **79,80 € HT/an, soit 6,65 € HT/mois**.
Le nouvel hébergement Scaleway coûte **29,48 € HT/mois** (control-01 14,74 + worker-01 14,74),
soit **4,4 fois plus, pour moins de processeur, de mémoire et de disque**. À mettre en regard de
ce qu'il apporte : machines reproductibles, déploiement sans compilation, plan de contrôle séparé.
**Inconnue à lever avant le 23/09/2026** : le prix de renouvellement du VPS OVH, la facture de 2025
étant une souscription (tarif de première année probable). Guilhem doit le vérifier dans son espace
client ; si le renouvellement reste autour de 7 €/mois, l'écart justifie de rouvrir le choix du
fournisseur pour le calcul (le DNS, lui, reste chez Scaleway et ne coûte rien).

- [x] Démo passée sur **`essai-3`** le 11/09/2026 : l'image `essai-2` ne contenait pas le correctif
  des index SQLite (PR #195, fusionnée après sa construction). Migration
  `add_missing_foreign_key_indexes_for_sqlite` désormais appliquée, 66 index contre 32.
  **Aucun client ne doit être migré sur une image antérieure à `essai-3`.**

**Outil de migration écrit le 11/09/2026** : `scripts/migrate-instance.py`, quatre commandes
(`ttl` la veille, `preparer` sans coupure, `basculer` dans le créneau, `verifier`). Il reprend
exactement la procédure jouée sur la démo, y compris les pièges : clé de chiffrement conservée,
extraction du storage sans `--strip-components`, redémarrage de Traefik après la bascule,
vérifications lancées depuis control-01. Testé sur la démo (commande `verifier`).
L'inventaire des cabinets est dans `clients.yaml`, non versionné.

**Décision de Guilhem le 11/09/2026 : on reste sur deux DEV1-M (29,48 € HT/mois).** Voir
DECISIONS § 9 pour le détail du comparatif et l'écart assumé avec OVH.

- [x] **Le back-office écrit lui-même les enregistrements DNS**, le 11/09/2026. Application IAM
  `backoffice-dns` créée par Guilhem, politique unique `DomainsDNSFullAccess` limitée au projet
  `ghosteo`, clé portée par l'application (et non par l'utilisateur). Jeton rangé chiffré dans les
  réglages du back-office (`scaleway_dns_token`), `dns_provider` passé à `scaleway`. Essai réel :
  `ScalewayDnsProvider` a posé `test-dns-auto.ghosteoapp.eu → 51.15.247.226` (TTL 300 s), vérifié
  sur le serveur de noms, puis supprimé. **Expiration de la clé : 11/09/2027** — la création de
  nouveaux clients cessera silencieusement ce jour-là si elle n'est pas renouvelée.

**Comment contrôler le périmètre d'une clé Scaleway, et comment NE PAS le faire** (erreur commise
le 11/09/2026, qui a fait refaire une clé pour rien à Guilhem) :

- `GET` sur une **liste** (`/instance/v1/.../servers`) renvoie **200 avec une liste vide** quand la
  clé n'a pas le droit. Un 200 ne prouve donc aucun droit.
- `POST` avec un corps invalide renvoie **400** même sans permission : Scaleway valide la forme de
  la requête **avant** les droits. Un 400 ne prouve donc aucun droit non plus.
- La seule sonde fiable est un `GET` sur une **ressource précise et existante**
  (`/servers/<id>`) : la réponse est alors `403 permissions_denied` avec le détail de la
  ressource et de l'action refusées.
- Pour l'écriture, poser un enregistrement réel puis le supprimer.

**Reste à faire pour clore la phase 4** : rien côté agent.

### Le moniteur montre la démo « plus lente » depuis la migration — explication (11/09/2026)

La courbe du moniteur monte après la bascule. **Ce n'est pas une dégradation** : c'est un
artefact de l'endroit d'où la sonde mesure.

La sonde tourne **sur le VPS OVH**. Avant la migration, la démo était sur cette même machine :
elle se mesurait elle-même, sans réseau. Depuis, la mesure traverse Internet jusqu'à Paris.

| Mesure | Démo (Scaleway) | Staging (resté sur le VPS) |
|---|---|---|
| Rendu de `/login` dans le conteneur, sans réseau | **20 à 27 ms** | 46 à 61 ms |
| Vu depuis le VPS, parcours complet d'un visiteur | 115 à 221 ms | 62 à 78 ms |
| Vu depuis la maison, parcours complet | **172 à 232 ms** | 170 à 204 ms |
| Latence réseau depuis la maison | 14,5 ms | 19,6 ms |

Autrement dit : l'application rend la page **deux fois plus vite** qu'avant (SQLite indexé,
image récente), et pour un vrai visiteur les deux hébergements sont équivalents, Scaleway étant
même un peu plus proche en réseau. Seule la sonde, qui a perdu son avantage de localité, voit
une hausse.

**Piège de méthode rencontré** : mesurer `http://127.0.0.1/` sur le worker avec un en-tête `Host`
ne mesure **que la redirection de Traefik** (1,5 ms), pas l'application. Pour chronométrer le
rendu réel, viser le conteneur : `docker exec <app>-web-1 curl http://127.0.0.1:8080/login`.

**Conséquence pour la phase 6** : quand ghosteo.eu quittera le VPS, la sonde mesurera toutes les
instances depuis Scaleway et les chiffres redeviendront comparables entre eux. Les seuils
d'alerte du moniteur seront à relire à ce moment-là.

### Défaut de la chaîne de livraison : le tag ne construit jamais l'image (12/09/2026)

`v1.17.0` a été livrée par Guilhem le 11/09/2026 à 23h51 (PR #201 fusionnée, tag posé, commit
`release: v1.17.0 (#201)` sur `main`). **Aucune image n'a été publiée**, toujours rien 40 min après.

Cause : `release.yml` pose le tag depuis le workflow, avec le `GITHUB_TOKEN` par défaut
(auteur `github-actions[bot]`). Or la documentation GitHub est explicite : « With the exception of
`workflow_dispatch` and `repository_dispatch`, other `GITHUB_TOKEN`-triggered events do not create
workflow runs at all. » Le déclencheur `push: tags: ["v*"]` de `docker.yml` ne se déclenche donc
jamais à la livraison. C'est aussi pourquoi `v1.16.0` n'a jamais eu d'image, et pourquoi seules
les images lancées à la main existent (`essai-1`, `essai-2`, `essai-3`).

- **Contournement immédiat** : onglet Actions → « Image Docker » → *Run workflow* → branche `main`,
  champ tag `1.17.0`. Produit la même image.
- **Correctif durable** : **PR ouverte** https://github.com/guim31/ghosteo/pull/202 le 12/09/2026.
  `docker.yml` devient appelable (`workflow_call`, entrées `tag` et `latest`) et `release.yml`
  l'appelle après la pose du tag. Le déclencheur `push: tags` est conservé pour un tag humain, le
  lancement manuel est inchangé, une seule construction par livraison. Les cinq cas de nommage ont
  été simulés hors CI. Alternative écartée : pousser le tag avec un jeton personnel, qui aurait mis
  un secret de longue durée dans le dépôt. **Retirer la permission « Workflows » du jeton GitHub
  après la fusion** (accordée par Guilhem le 12/09/2026).

### Version 1.17.0 en service (12/09/2026)

- Livrée par Guilhem (PR #201), tag `v1.17.0` posé, **image construite à la main** faute du
  déclenchement automatique ci-dessus : `ghcr.io/guim31/ghosteo:1.17.0` (993 Mo, 12/09 05:51).
  Pas de tag `latest` : le lancement manuel ne le pose pas, seul l'appel corrigé le fera.
- **Démo passée en 1.17.0** : 71 patients, 747 consultations, 2 comptes, déchiffrement OK,
  `hardware_id` conservé, aucune migration en attente, HTTPS et redirections correctes.
- Image par défaut du back-office portée à `ghcr.io/guim31/ghosteo:1.17.0`. **Le réglage s'appelle
  `deploy_image`** et non `dokploy_default_image` : ma première écriture a créé une clé inutile,
  supprimée depuis. Vérifier le nom dans `SettingController` avant d'écrire un réglage par tinker.
- **C'est la première image déployable chez un client** : les `essai-*` ne sont plus à utiliser.

## Phase 5 — Clients

**Deux cabinets ne sont pas en métropole** (indiqué par Guilhem le 11/09/2026). Une soirée
française y est le milieu de la journée de travail : migrer à l'heure locale du praticien,
pas à la nôtre. Guilhem n'autorise la mise en maintenance que pendant **leur** nuit.

| Instance | Lieu | Décalage / Paris | Leur nuit 22h-05h, en heure de Paris |
|---|---|---|---|
| `anais-delaunay` | Nouvelle-Calédonie | +9 h (été) / +10 h (hiver) | 13h00 → 20h00 (été) ; 12h00 → 19h00 (hiver) |
| `aurelien-marie-joseph` | Martinique | −6 h (été) / −5 h (hiver) | 04h00 → 11h00 (été) ; 03h00 → 10h00 (hiver) |

Le changement d'heure français du 25/10/2026 décale ces créneaux d'une heure : recalculer
après cette date. Les cinq autres cabinets sont en métropole, créneau de soirée habituel.



| Client | Créneau | Migré le | Vérifié par le client | Ancienne instance éteinte le |
|---|---|---|---|---|
| Guilhem HENRY | 12/09 08h29 | **12/09/2026**, coupure 3 min 30 | à faire | après le 12/10/2026 |
| Xavier PAGES | 12/09 21h00 | **12/09/2026** | à faire | après le 12/10/2026 |
| Cédric ROUSSEAU | 13/09 08h25 | **13/09/2026**, coupure 6 min | à faire | après le 13/10/2026 |
| Aurélien MARIE-JOSEPH *(Martinique, 04h-11h heure de Paris)* | 12/09 09h06 Paris = 03h06 chez lui | **12/09/2026**, coupure 3 min 30 | prévenu par message le 12/09, réponse attendue à son réveil | après le 12/10/2026 |
| Alexia GAUTHIER | 13/09 08h22 | **13/09/2026**, coupure 3 min | à faire | après le 13/10/2026 |
| Adrien BLACHON | 13/09 08h31 | **13/09/2026**, coupure 5 min | à faire | après le 13/10/2026 |
| Anaïs DELAUNAY *(Nouvelle-Calédonie, 13h-20h heure de Paris)* | 12/09 14h07 Paris = 00h07 chez elle | **12/09/2026**, coupure 8 min | à faire | après le 12/10/2026 |

### Cabinet de Guilhem migré le 12/09/2026 — première migration réelle

Instance #1, `guilhem-henry.ghosteoapp.eu`, sur worker-01 : service `a3fvfc_4BC2u4uUJ2Ww1t`
(appName `ghosteo-guilhem-henry-17omke`), image **1.17.0**, certificat jusqu'au 11/12/2026.
**Coupure de 3 min 30** (maintenance à 08h29, HTTPS rétabli à 08h32).

Comparaison ancienne / nouvelle, identique sur toute la ligne :

| | patients | consultations | comptabilités | comptes | fichiers patients |
|---|---|---|---|---|---|
| Ancienne (MySQL) | 5 075 | 19 863 | 19 944 | 7 | 40 |
| Nouvelle (SQLite) | 5 075 | 19 863 | 19 944 | 7 | 40 |

54 130 lignes copiées dans 30 tables. Déchiffrement vérifié sur un nom réel, `hardware_id`
conservé (`6b966a2e…`), licence `GHOSTEO-YOPTEBPTN-MCYQP4RT` intacte, 22 documents patients et
24 Mo restaurés, aucune migration en attente. Worker-01 : **2 instances sur 12**, 961 Mo de RAM
utilisés sur 3 909. L'ancienne instance reste en maintenance sur le VPS, intacte, jusqu'au
12/10/2026 au moins.

### Cabinet d'Aurélien MARIE-JOSEPH migré le 12/09/2026 (Martinique)

Instance #5 sur worker-01 : service `E4k7q9ouYZhkfw_0Qq8gs`
(appName `ghosteo-aurelien-marie-joseph-ehuq8j`), image 1.17.0, certificat jusqu'au 11/12/2026.
Bascule à 09h06 heure de Paris, soit **03h06 chez lui**, dans le créneau autorisé par Guilhem.
**Coupure de 3 min 30** (09h06 → 09h09).

| | patients | consultations | comptabilités | comptes | fichiers patients |
|---|---|---|---|---|---|
| Ancienne (MySQL) | 3 805 | 6 493 | 6 493 | 2 | 6 |
| Nouvelle (SQLite) | 3 805 | 6 493 | 6 493 | 2 | 6 |

21 275 lignes dans 30 tables, déchiffrement vérifié, `hardware_id` conservé, licence
`GHOSTEO-VIP-WHVZOLXVPPRG` intacte, volume de 18 Mo. Le script a tourné **sans aucune
intervention** : première migration entièrement automatique.

Worker-01 après deux cabinets et la démo : **3 instances sur 12**.

### Mesure sérieuse du coût mémoire d'une instance (12/09/2026)

Question de Guilhem : passer de 2 à 3 instances n'a ajouté que 160 Mo au « used » de `free`,
ce qui ne collait pas. En effet : **`free` et `docker stats` ne servent à rien ici**, ils
mélangent mémoire réellement occupée et cache de fichiers, lequel est récupérable et surtout
**partagé entre instances** (même image, mêmes couches). La bonne mesure est
`memory.stat` du cgroup, en additionnant `anon`, `shmem`, `kernel` et `slab`.

| Conteneur | anon | partagée | noyau | non récupérable |
|---|---|---|---|---|
| `web` | 11 Mo | 24-31 Mo | 9-11 Mo | **45 à 53 Mo** |
| `scheduler` | 17 Mo | 27 Mo | 4 Mo | **48 Mo** |
| `queue` | 18 Mo | 27 Mo | 4 Mo | **50 Mo** |
| **une instance complète** | | | | **≈ 148 Mo** |

Modèle validé par le total système : les 10 conteneurs pèsent 462 Mo, et
`AnonPages + Shmem + SUnreclaim` du système vaut 697 Mo — soit **235 Mo pour l'hôte**
(système, dockerd, containerd, fail2ban, noyau) et 18 Mo pour Traefik.

**Projection corrigée pour un DEV1-M (3 909 Mo)** : 235 (hôte) + 18 (Traefik) + 12 × 148
= **2 029 Mo**, soit 52 % de la machine. Il reste environ 1,9 Go pour le cache et les pointes.
Le plafond de 12 est donc tenable. *(La projection annoncée plus haut, « environ 2,6 Go », était
juste par accident : elle partait d'un chiffre `docker stats` qui approximait le bon total pour
de mauvaises raisons.)*

**Coût de la charge, mesuré** : 12 requêtes simultanées sur une instance font passer son
conteneur `web` de 13 à 38-51 Mo d'`anon` et ouvrent 12 processus PHP, qui disparaissent en
moins de 25 s (PHP-FPM en mode `ondemand`). Soit **+25 à 38 Mo pour une instance saturée**, et
2 à 3 Mo par requête concurrente seulement : l'essentiel du processus PHP est partagé avec son
parent. Un cabinet de deux ou trois praticiens ne dépassera pas quelques mégaoctets.

**Deux leviers si la place venait à manquer**, dans cet ordre :

1. **Les conteneurs `scheduler` et `queue` coûtent 98 Mo des 148**, soit deux tiers, pour deux
   processus qui dorment (0,1 % de CPU). Leur `shmem` de 27 Mo chacun est le cache de code PHP :
   `opcache.memory_consumption` vaut 128 Mo alors que **8 Mo seulement sont utilisés**, et
   `opcache.enable_cli` est actif. Le réduire dans l'image économiserait ~50 Mo par instance,
   soit 600 Mo à douze cabinets. Pas urgent : **issue https://github.com/guim31/ghosteo/issues/203**
   ouverte le 12/09/2026, texte conservé dans `notes/issue-opcache.md`. La permission « Issues »
   du jeton GitHub a été ajoutée à cette occasion (distincte de « Pull requests ») ; elle peut
   rester, elle ne donne accès qu'aux tickets.
2. Repasser worker-01 en DEV1-L (8 Go, 31,27 €), ou créer worker-02. Le changement de taille
   prend 2 min 30 et ne demande pas de recréer la machine.

**Deux défauts du script corrigés au passage, avant toute coupure** :

1. **La conversion tournait sur control-01, qui ne peut pas tirer l'image privée.** Seul le
   worker a des identifiants de registre (posés par Dokploy au test de registre) ; control-01
   n'en a aucun et n'avait en cache que les images `essai-*`. Le répertoire de travail vit
   désormais **sur le worker** : l'image y est, les données y arrivent de toute façon, et elles
   ne transitent plus ni par le Beelink ni par le serveur de contrôle.
2. **L'échec était masqué par un `| tail -2`** : le code de sortie d'un tube est celui de sa
   dernière commande, donc `set -e` ne voyait rien et le script continuait avec une base vide.
   Corrigé par `set -o pipefail`. Sans cette découverte, la bascule aurait installé une base
   vide chez un client.

### Bascules programmées le 12/09/2026

Tous les clients ont été prévenus par Guilhem. Deux entrées de crontab **sur le Beelink**
(donc durables, contrairement à un minuteur interne à l'agent, qui disparaîtrait au
redémarrage du superviseur) :

| Heure | Cabinets | Heure locale du praticien |
|---|---|---|
| 14h07 | `anais-delaunay` | 00h07 en Nouvelle-Calédonie |
| 21h00 | `xavier-pages`, `cedric-rousseau`, `alexia-gauthier`, `cabinet-blachon-thivillier` | idem, métropole |

Les deux lignes portent `--auto-retrait` : `cutover.sh` retire sa propre entrée de crontab
après exécution. Une bascule est un geste unique ; une entrée oubliée rejouerait la migration
d'un cabinet déjà migré, avec les données devenues obsolètes du VPS.

**Les cinq instances sont préparées** (`preparer`, sans coupure) et attendent leur créneau :
sauvegarde à chaud, conversion, contrôle de conformité, création du service, déploiement.
Conteneurs sains, adresses encore sur l'ancien serveur. Worker-01 : 8 instances (3 en service,
5 en attente), 1 781 Mo de RAM sur 3 909, disque à 37 %.

**Faux positif du garde-fou, corrigé** : les quatre premières préparations ont été refusées
alors que les copies étaient exactes (7 011 patients pour 7 011, 10 952 pour 10 952). Le
comptage source parlait « utilisateurs » quand la copie parlait « users » : le comparateur
concluait à une table manquante. Corrigé en n'employant que des noms de tables, et durci —
il refuse désormais de conclure s'il n'a aucune table en commun à comparer, au lieu de
traiter une absence comme un écart. Éprouvé sur trois cas : copie conforme, écart réel,
absence de correspondance. **Le sens de l'échec était le bon** : refuser de basculer plutôt
que laisser passer une copie douteuse.

Journal des bascules : `~/ghosteo-bascule.log` sur le Beelink.

### Garde-fous ajoutés avant d'automatiser (12/09/2026)

Une bascule sans surveillance n'était pas acceptable en l'état. Quatre ajouts :

1. **Contrôle de conformité de la copie** (`verifier_conversion`) : les comptes de la base
   SQLite produite sont comparés à ceux de la source MySQL, table par table, **avant**
   d'installer quoi que ce soit et avant de toucher au DNS. En cas d'écart, rien ne bascule.
   Testé en injectant un faux compte source : l'exécution s'arrête bien.
2. **Retour arrière automatique** (`retour-arriere`) : rend l'adresse à l'ancien serveur, puis
   sort l'ancienne instance de maintenance — dans cet ordre, l'inverse ferait servir deux
   instances différentes selon le cache du visiteur. Appelé par `cutover.sh` à tout échec.
3. **Maintenance et rattachement dans l'outil** (`maintenance`, `service`, `backoffice`) : plus
   de gestes manuels dans le créneau, et le back-office se rattache par URL, sans identifiant
   codé en dur.
4. **`python3 -u` dans `cutover.sh`** : sans cela Python garde sa sortie en mémoire jusqu'à la
   fin et le journal reste muet pendant toute la bascule — inacceptable pour surveiller a
   posteriori.

**Piège de quoting, rencontré trois fois** : `ssh … sudo -u X bash -c "… php artisan tinker
--execute='…'"` est ingérable et **échoue en silence** (la commande est mal découpée, le code de
retour reste 0). Tout PHP ou artisan distant part désormais par l'entrée standard d'un script
(`ssh VPS bash -s` avec un heredoc), comme `scripts/remote-counts.sh`.

### Incident : clé de chiffrement d'une instance exposée (12/09/2026)

En diagnostiquant la lenteur apparente d'une préparation, l'agent a affiché la liste des
processus du worker. Or la conversion passait alors ses secrets **en ligne de commande**
(`docker run -e APP_KEY=… -e SOURCE_DB_PASSWORD=…`), donc visibles dans
`/proc/<pid>/cmdline` et dans cette sortie. Se sont retrouvés dans la conversation :

- l'**`APP_KEY` de l'instance `anais-delaunay`** — sérieux : cette clé chiffre les champs
  patients (nom, adresse, téléphone, numéro de sécurité sociale…) **et signe les cookies de
  session**, donc elle vaut identifiant d'accès à son instance ;
- un mot de passe MySQL temporaire, sans portée (le conteneur est détruit à la fin).

**Corrigé** : les secrets passent par un fichier `--env-file` en mode 600, effacé au `shred`
après usage. Vérifié : plus aucun secret dans les lignes de commande générées.

**Décision de Guilhem, 12/09/2026 : risque accepté, pas de rotation.** La clé d'
`anais-delaunay` reste en place. Le raisonnement : la conversation est privée, et la clé seule
ne donne pas accès aux dossiers, il faudrait aussi la base.

Pour mémoire si la question se rouvrait un jour : la rotation est possible mais **aucune
commande ne l'implémente** dans `ghosteo`. La voie propre est `APP_PREVIOUS_KEYS` de Laravel,
qui déchiffre avec l'ancienne clé pendant qu'on réenregistre les données avec la nouvelle ;
il faudrait une commande artisan parcourant tous les modèles à champs `encrypted`. Les champs
concernés sur `Patient` : nom, nom d'usage, prénom, adresse, téléphones, e-mail, numéro de
sécurité sociale.

### Cabinet d'Anaïs DELAUNAY migré le 12/09/2026 (Nouvelle-Calédonie)

**Première bascule entièrement automatique**, lancée par la crontab à 14h07 heure de Paris,
soit 00h07 chez elle. Terminée à 14h15 : maintenance, sauvegarde à froid, conversion, contrôle
de conformité (« copie conforme à la source »), installation, bascule d'adresse, certificat,
vérification, rattachement au back-office, puis retrait de sa propre ligne de crontab.
Instance #9 sur worker-01, service `ghosteo-anais-delaunay-x74jan`, certificat jusqu'au
11/12/2026. Aucune intervention humaine.

| | patients | consultations | comptabilités | comptes | fichiers patients |
|---|---|---|---|---|---|
| Ancienne (MySQL) | 6 204 | 17 290 | 17 290 | 3 | 178 |
| Nouvelle (SQLite) | 6 204 | 17 290 | 17 290 | 3 | 178 |

Déchiffrement vérifié, `hardware_id` conservé, licence `active` sans mode dégradé, aucune
migration en attente. Worker-01 : 8 instances, 1 827 Mo de RAM sur 3 909, disque à 39 %.

### Aurélien signale que son site ne fonctionne plus (12/09/2026, ~13h30)

Guilhem le teste depuis chez lui : ça marche. Investigation côté serveur, **rien trouvé** :

| Contrôle | Résultat |
|---|---|
| Enregistrement A, chez Scaleway et chez Cloudflare, Google, Quad9 | `51.15.247.226`, correct partout |
| Enregistrement AAAA (piste IPv6) | aucun, sur aucun résolveur |
| Conteneurs de son instance | les trois sains, `web` *healthy* |
| Ancien serveur, s'il est encore atteint | 503, maintenance — **ce qu'il verrait si son DNS était périmé** |
| Nouveau serveur | 302 vers `/login`, puis 200 |
| Licence | `active`, pas de mode dégradé, ping au serveur de licence réussi |
| Comptes | `#1` inactif, `#2` actif — **identique à l'ancienne instance**, rien n'a changé |
| Chaîne de certificat | complète (feuille + YR1 + ISRG Root YR), `Verify return code: 0` |
| En-têtes servis | 302 vers la bonne URL, cookies posés, HSTS présent |

**Le fait qui oriente** : en trois heures, **une seule** requête de son côté est arrivée sur la
nouvelle instance, depuis un iPhone à 12h42 UTC ; elle a reçu le 302 et n'a pas suivi vers
`/login`. Tout le reste du trafic vient de la maison de Guilhem, du moniteur et de sondes.

Hypothèse de tête, cohérente avec ces faits : **son résolveur DNS (téléphone, box ou
fournisseur) sert encore l'ancienne adresse**, où l'instance est en maintenance. Il verrait
donc une page de maintenance, ce qui se raconte comme « le site ne fonctionne plus ». Le test
qui tranche en dix secondes : lui faire couper le Wi-Fi pour passer en données mobiles, ce qui
change de résolveur.

**Cause trouvée, et reproduite** (12/09/2026). Aurélien a essayé en navigation privée : ça
fonctionne. Ce n'était donc ni le DNS ni le serveur, mais une donnée conservée par son
navigateur. Reproduction sur la démo, en supprimant les sessions puis en rejouant son cas :

| Situation | Réponse |
|---|---|
| Visite avec un cookie de session devenu orphelin | **200**, aucun problème |
| Envoi du formulaire avec l'**ancien jeton anti-CSRF** (page ouverte ou en cache d'avant la migration) | **419 « Session expirée »** |
| Même envoi avec un jeton frais | 302, connexion normale |

`app:copy-database` exclut volontairement la table `sessions` (elle est dans sa liste `SKIP`,
avec `cache`, `jobs`…). **Tout client connecté est donc déconnecté par la migration**, ce qui
est sain. Mais s'il avait la page de connexion ouverte ou en cache, son jeton anti-CSRF est
périmé et l'envoi du formulaire renvoie une page « Session expirée » — que le praticien lit
comme « mon logiciel ne marche plus ».

**Ce n'est pas un incident, c'est un effet de bord prévisible de toute migration**, et il
touchera les quatre cabinets de ce soir. La parade est un message, pas du code : après la
bascule, **recharger la page** (ou fermer puis réouvrir l'onglet) avant de se reconnecter.
À ajouter au message type envoyé aux clients, dans le guide.

**Amélioration possible, à ne pas faire dans l'urgence** : la page 419 de GHosteo est soignée
(titre « Session expirée - GHosteo ») mais c'est un cul-de-sac. Beaucoup d'applications
Laravel renvoient l'utilisateur vers la page de connexion avec un jeton frais et un message,
plutôt que de l'y laisser. Candidat à une issue sur `ghosteo`.

**Détail relevé au passage, à nettoyer sans urgence** : l'en-tête
`strict-transport-security` est émis **deux fois**, par nginx dans l'image et par Traefik.
Sans effet fonctionnel, mais à dédoublonner.

## Refonte du moniteur d'instances (demandée le 12/09/2026)

Quatre demandes de Guilhem : des métriques serveur utiles (Vito n'en remonte presque pas),
surveiller les bons serveurs (le VPS Vito n'aura bientôt plus de sens), obtenir la version
déployée sans attendre qu'un client se connecte, et raccourcir la liste de 100 lignes en bas
de la fiche d'instance.

### Ce qui existe aujourd'hui, et pourquoi ça casse

- `HostMetricsReader` lit le `/proc` **de la machine qui exécute le back-office**. Cela marche
  tant que ghosteo.eu est colocalisé avec les instances sur le VPS Vito. Dès la phase 6, il
  rapportera les chiffres de control-01 et non ceux du worker : faux, pas seulement inutile.
- `VersionService` déduit la version de chaque instance de ce que remonte le ping de licence,
  et la version de référence est la plus élevée observée. D'où « 4/9 à jour » alors que les
  instances migrées tournent en 1.17.0 : les autres n'ont pas encore pingé.
- `InstanceController` charge `limit(100)` contrôles sans pagination (ligne 86).

### Ce que l'agent de métriques Dokploy sait faire (mesuré)

Activé sur les deux serveurs le 12/09/2026 (`admin.setupMonitoring` pour le panneau,
`server.setupMonitoring` pour le worker). Conteneur `dokploy/monitoring:latest`, **24 Mo de
mémoire**, écoute sur le port 4500, jeton dans `~/.config/dokploy/metrics.token` du Beelink.

Données renvoyées par `/metrics`, bien plus riches que Vito : `cpu` %, modèle et nombre de
cœurs, fréquence, OS, noyau, architecture, `memUsed` en % **et en Go**, `memTotal`,
`diskUsed` %, `totalDisk`, `networkIn`/`networkOut`, `uptime`. `/metrics/containers` existe
aussi, pour un suivi par instance.

**Deux pièges relevés** : l'image est en `:latest`, non épinglée, contrairement à la règle
posée pour Dokploy lui-même. Et la route `server.getServerMetrics` de l'API Dokploy **ne
fonctionne pas** (« fetch failed ») : le conteneur Dokploy n'atteint pas l'agent qui écoute
sur l'hôte. Lire l'agent directement est de toute façon préférable — un appel HTTP de moins
et aucune dépendance à une API jeune.

### Ce qui est fait : PR https://github.com/guim31/ghosteoeu-main/pull/63 (12/09/2026)

- **Un bloc de métriques par serveur déclaré**, alimenté par `AgentMetricsReader` qui lit
  l'agent directement (un GET, pas de dépendance à l'API du panneau). Le relevé de la machine
  du moniteur ne s'affiche plus que si elle porte encore des instances, sous le titre
  « Ancien hébergement », et disparaîtra de lui-même.
- **Version déployée lue dans `GHOSTEO_IMAGE`** (`DokployClient::deployedVersion`), donc
  immédiate. Les deux versions sont conservées : un écart signale un conteneur redéployé mais
  pas redémarré. `Instance::effectiveVersion()` et `versionMismatch()`.
- **Liste des contrôles paginée** par 20 au lieu de 100 lignes d'un coup.
- Nouvelles colonnes : `servers.metrics_host`, `servers.metrics_port`,
  `instances.deployed_version`, `instances.deployed_version_at`. Nouveau réglage chiffré
  `metrics_agent_token`.
- Contrôles sur le banc du NAS : Pint 292 fichiers, **423 tests**, PHPStan sans erreur.
  *Piège du banc* : PHPStan meurt en « 4 errors » trompeuses si la mémoire PHP reste à 256 Mo.
  Lancer avec `--memory-limit=1G`.

### Réseau privé en place (12/09/2026)

Après ajout de `PrivateNetworksFullAccess` par Guilhem : VPC `ghosteo`
(`e4df5e22-69dc-4b9e-9567-b00c800da084`), réseau privé **`ghosteo-interne`**
(`1ad7d2d4-be8b-4395-82b6-26681b3a0bf2`, sous-réseau `172.31.40.0/22`).

| Serveur | Adresse privée |
|---|---|
| control-01 | `172.31.40.2` |
| worker-01 | `172.31.40.3` |

Vérifié : les métriques des deux serveurs se lisent par le réseau privé, et le port 4500
**reste fermé depuis l'extérieur**. Le relevé ne traverse donc jamais l'Internet public,
ce qui importe puisque l'agent ne parle que HTTP.

**Trois pièges rencontrés, tous consignés dans les scripts** :

1. Le chemin d'API est `/servers/<id>/private_nics`. `/private_nics` seul renvoie 404.
2. La carte privée monte mais **reste sans adresse** : il faut un fichier netplan qui
   demande le bail DHCP. Deux dérogations y sont indispensables, `use-routes: false` et
   `use-dns: false` — sans elles le réseau privé installerait une route par défaut et
   remplacerait la résolution DNS du serveur. Même erreur que le tunnel VPN du travail.
   Appliqué avec un filet de sécurité (retour arrière automatique à 180 s si l'accès SSH
   se perdait) ; la route par défaut et le DNS sont restés intacts, vérifié.
3. **`ufw` bloquait le port 4500**, y compris sur le réseau privé. Règle ajoutée sur les
   deux serveurs, restreinte à `172.31.40.0/22`, et reportée dans `cloud-init/worker.yaml`
   pour les prochains. `create-server.py` reçoit `--reseau-prive <id>` et imprime le
   fichier netplan prêt à coller, adresse MAC comprise.

**Limite à connaître** : ghosteo.eu tourne encore sur le VPS OVH, hors de ce réseau privé.
Les métriques ne s'afficheront donc qu'après la bascule du back-office (phase 6). D'ici là
`servers.metrics_host` reste vide et l'écran le dit explicitement, plutôt que d'échouer
toutes les minutes. Valeurs à saisir le jour J : `172.31.40.2` et `172.31.40.3`.

### Refonte du moniteur en service (12/09/2026)

PR #63 fusionnée à 17h47 et **déployée par Guilhem depuis Vito** — le déploiement par
l'agent est refusé par son contrôle d'autorisations, et c'est cohérent : c'est un
`git reset --hard` suivi d'un build et de migrations sur le serveur de licences dont
dépendent toutes les instances. Les quatre colonnes sont en place, le réglage
`metrics_agent_token` est saisi et chiffré en base (copies temporaires effacées des deux
machines).

Premier relevé, qui valide la fonctionnalité **et trouve deux choses** :

| Instance | Image déployée | Version annoncée |
|---|---|---|
| Guilhem HENRY | 1.17.0 | 1.17.0 |
| Demo DEMO | 1.17.0 | **1.16.0** |
| Aurélien MARIE-JOSEPH | 1.17.0 | 1.17.0 |
| Anaïs DELAUNAY | 1.17.0 | 1.17.0 |
| Staging SCALEWAY | **essai-2** | 1.16.0 |

- La démo affiche l'écart attendu : elle est bien en 1.17.0 mais personne ne s'y est
  connecté depuis, donc son ping de licence annonce encore l'ancienne. C'est exactement le
  cas que la colonne sait désormais distinguer, et qui restait invisible avant.
- **La recette tournait encore sur `essai-2`**, image d'essai antérieure au correctif des
  index SQLite. Passée en 1.17.0 le 12/09/2026. Sans la version déployée, ce retard était
  indétectable : son ping annonçait 1.16.0 comme trois autres instances.

Référence du parc : 1.17.0. À jour : 5 / 9. Écarts image/annonce : 1.

`servers.metrics_host` reste **vide jusqu'à la phase 6**, ghosteo.eu étant hors du réseau
privé. Valeurs du jour J : control-01 → `172.31.40.2`, worker-01 → `172.31.40.3`.

### Le point de transport

**VPC créé** le 12/09/2026 (`ghosteo`, `e4df5e22-69dc-4b9e-9567-b00c800da084`) après ajout de
`VPCFullAccess` par Guilhem. Mais la création du **réseau privé** reste refusée : la ressource
s'appelle `compute_private_networks` et demande une permission distincte, vraisemblablement
`PrivateNetworksFullAccess`, à ajouter à la politique `beelink-migration`.

Tant que le réseau privé n'existe pas, `metrics_host` reste vide et les blocs affichent
« Aucune adresse d'agent de métriques renseignée » — explicitement, et non un tiret muet.
À noter : le back-office tourne encore sur le VPS OVH, hors du futur réseau privé ; les
métriques ne seront donc complètes qu'après la bascule de ghosteo.eu (phase 6).



Le port 4500 du worker **n'est pas joignable depuis le panneau** (groupe de sécurité : 22, 80,
443 seulement). Vérifié. Trois voies :

| Voie | Avantage | Inconvénient |
|---|---|---|
| Réseau privé Scaleway (VPC) | le plus propre, gratuit, rien d'exposé | la clé du Beelink **n'a pas le droit VPC** ; demande une permission et un rattachement des deux machines |
| Publier l'agent en HTTPS derrière Traefik | chiffré, aucune règle de pare-feu à ajouter | crée une adresse publique de plus, protégée par le seul jeton |
| Ouvrir 4500 à la seule IP du back-office | simple | **jeton en clair sur Internet**, l'agent ne fait que du HTTP |

### Échec des bascules du 12/09 à 21h : quota de certificats Let's Encrypt

**Un cabinet sur quatre est passé.** Xavier Pagès migré et vérifié. Cédric Rousseau, Alexia
Gauthier et Adrien Blachon ont échoué sur « pas de certificat après 5 minutes » et ont été
**rendus à l'ancien serveur par le retour arrière automatique** : aucun client n'a été coupé
au-delà de sa fenêtre, les trois répondaient en 200 dans la minute.

**Cause, en deux fautes de conception de la procédure, pas une panne.**

1. **Le domaine était déclaré dans `preparer`, avant la bascule d'adresse.** Traefik demandait
   donc le certificat pendant que le nom pointait encore vers l'ancien serveur : le défi ACME
   échouait. Or Let's Encrypt n'accorde que **cinq échecs de validation par nom et par heure**,
   et chaque redémarrage du routeur — que la procédure faisait à chaque bascule — relançait une
   tentative pour *tous* les noms en attente. Les trois derniers cabinets avaient épuisé leur
   quota avant même leur tour. Xavier est passé parce qu'il était premier.
2. **Les vérifications passaient par un résolveur.** Le cache DNS de control-01 a fait prendre
   l'ANCIEN serveur pour le nouveau, et une bascule ratée pour une réussie : à 23h24 le script
   a annoncé « certificat en place » en mesurant en réalité l'ancienne instance. C'est la
   troisième fois que ce cache trompe une vérification.

**Troisième enseignement, découvert en réparant** : `domain.delete` retire le domaine de la
base de Dokploy mais **pas les étiquettes Traefik des conteneurs déjà créés**, et
`compose.redeploy` ne les régénère pas. Traefik continue donc de voir le nom et de retenter
ACME, consommant le quota en silence. Inerte tant que le DNS pointe ailleurs et que le routeur
n'est pas redémarré, mais à savoir.

**Corrections apportées le 12/09/2026 au soir :**

- `declarer_domaine()` : le domaine n'est déclaré **qu'après** la bascule d'adresse, suivi d'un
  redéploiement (les étiquettes Traefik se posent à la création des conteneurs). Le
  redémarrage de Traefik disparaît, devenu inutile.
- **Marge de 90 s après la bascule DNS** avant de déclarer le domaine : le serveur de noms est
  à jour immédiatement, mais Let's Encrypt valide depuis ses propres résolveurs, qui peuvent
  servir l'ancienne réponse pendant la durée du TTL (60 s).
- **Tous les contrôles HTTPS visent l'adresse du serveur d'accueil** (`curl --resolve`), sans
  jamais passer par un résolveur. Éprouvé sur Xavier : DNS conforme, `/up` et `/login` 200,
  certificat à son nom.
- `cutover.sh` **s'arrête au premier échec** quand plusieurs cabinets sont demandés, et signale
  les non tentés. Enchaîner malgré un échec a coûté trois cabinets au lieu d'un, la cause étant
  commune et chaque tentative l'aggravant.

**La reprise de 00h35 a échoué avant d'avoir rien touché** — et pour une tout autre raison :
`Temporary failure in name resolution` **sur le Beelink**. Le script n'a pas pu joindre les API
Scaleway et Dokploy, s'est arrêté à sa première instruction, et le retour arrière a échoué de
la même façon. Aucun client n'a bougé : la mise en maintenance n'avait pas eu lieu. Le résumé
« RETOUR ARRIÈRE EN ÉCHEC » est donc alarmiste à tort — vérifié, les quatre cabinets
répondaient en 200.

**Deuxième panne de résolution DNS du Beelink dans la journée** (la première vers 17h40, sur
un appel à l'API Scaleway). Le Beelink résout via la passerelle UniFi (192.168.100.1), pas
directement par AdGuard. Dix essais consécutifs réussissent ce matin : la panne est
intermittente. **À diagnostiquer séparément** : c'est le résolveur de toute la maison.

**Correctif apporté le 13/09/2026** : `scw.py` et `dokploy.py` rejouent un appel quand la
couche transport lâche (jusqu'à quatre tentatives, délai croissant), mais **jamais sur une
erreur HTTP** — une réponse du serveur doit remonter telle quelle. Une panne de résolution de
quelques secondes n'interrompt plus une migration en plein créneau.

**État au 13/09 08h15** : quota Let's Encrypt libéré depuis longtemps (dernière tentative ACME
le 12/09 à 23h28), procédure corrigée et éprouvée, trois instances prêtes et leurs données
déjà converties. Il ne manque qu'un créneau : les clients avaient été prévenus pour samedi
21h, le choix du nouveau moment revient à Guilhem.

### Les trois derniers cabinets migrés le 13/09/2026, 08h22 à 08h36

Procédure corrigée, **trois sur trois du premier coup, sans intervention**. Chaque certificat
obtenu dès la première demande : la marge de 90 s après la bascule DNS suffit à ce que les
résolveurs de Let's Encrypt aient oublié l'ancienne adresse.

| Cabinet | patients | consultations | comptabilités | comptes | ancien = nouveau |
|---|---|---|---|---|---|
| Alexia GAUTHIER | 12 | 24 | 24 | 2 | oui |
| Cédric ROUSSEAU | 10 952 | 40 816 | 39 991 | 3 | oui |
| Adrien BLACHON | 5 112 | 10 840 | 9 801 | 6 | oui |

Déchiffrement vérifié sur un dossier réel de chacun, `hardware_id` conservé, aucune migration
en attente, certificats à leur nom jusqu'au 11 ou 12/12/2026, redirection HTTP correcte.
Contrôles faits **en visant l'adresse du serveur**, plus par un résolveur.

**Les sept cabinets sont migrés.** Worker-01 : 8 instances (7 cabinets + la démo), 1 835 Mo de
RAM sur 3 909, disque à 47 %. La projection de 148 Mo par instance se confirme.

**Ce que cette phase 5 a coûté et appris.** Quatre bascules réussies du premier coup (Guilhem,
Aurélien, Anaïs, Xavier), trois échecs le 12/09 au soir tous dus à la même faute de procédure
— déclarer le domaine avant la bascule d'adresse — puis trois réussites après correction.
Aucune donnée perdue, aucun client coupé plus longtemps que sa fenêtre : le retour arrière
automatique a fonctionné à chaque fois.

## Phase 6 — Fin

- [ ] ghosteo.eu basculé sur control-01
- [ ] `servers.metrics_host` renseigné (`172.31.40.2`, `172.31.40.3`) : les métriques du
      moniteur ne s'allument qu'une fois le back-office dans le réseau privé
- [ ] Sauvegarde finale de l'ancien serveur sur Object Storage
- [ ] VPS OVH résilié
- [ ] Clés Scaleway et Dokploy révoquées et recréées

### Ce que la phase 6 doit savoir avant de commencer

**ghosteo.eu n'est pas une instance cliente.** `migrate-instance.py` ne convient pas tel
quel : il suppose SQLite, un service compose GHosteo et un volume `storage`. Le back-office
est une autre application, avec sa propre base et ses propres réglages chiffrés. La bascule
demande donc un travail à part, à concevoir — les briques réutilisables sont la sauvegarde
(`remote-dump.sh`), la conversion si l'on veut SQLite, et la méthode DNS (TTL abaissé la
veille, domaine déclaré **après** la bascule, marge de 90 s).

**Trois pièges qui ont coûté cher en phase 5, à ne pas réapprendre :**

1. Déclarer le domaine avant la bascule DNS fait échouer ACME et épuise le quota de
   Let's Encrypt (cinq échecs par nom et par heure). Déclarer après, avec 90 s de marge.
2. Toute vérification qui passe par un résolveur peut mesurer l'ancien serveur et faire
   passer un échec pour une réussite. Viser l'adresse (`curl --resolve`).
3. `domain.delete` ne retire pas les étiquettes Traefik des conteneurs déjà créés.

**Points ouverts sans rapport avec la phase 6**, à ne pas perdre :

- Le résolveur DNS du Beelink tombe par intermittence (deux fois le 12/09). Il résout via la
  passerelle UniFi alors qu'AdGuard tourne sur le Beelink lui-même : aller-retour inutile,
  et le Beelink perd son DNS si la boucle se casse. Diagnostic proposé, non fait.
- Issue https://github.com/guim31/ghosteo/issues/203 : réduire le cache de code PHP,
  environ 50 Mo par instance.
- L'en-tête `strict-transport-security` est émis deux fois, par nginx et par Traefik.
- Les sept cabinets doivent confirmer, chacun, qu'ils se connectent normalement.

### Plan de bascule de ghosteo.eu, proposé et accepté le 13/09/2026

**Ce que ghosteo.eu est réellement sur le VPS** (relevé du 13/09) : une application Laravel
distincte des instances, sous l'utilisateur `ghosteoserver`, servie pour `ghosteo.eu` **et**
`www.ghosteo.eu`. Base **MySQL 8.4** `ghosteoserver_db`, **7,7 Mo**, 30 tables : sessions,
cache et file d'attente y sont aussi (`SESSION_DRIVER`, `CACHE_STORE`, `QUEUE_CONNECTION`
= `database`). `storage/app` pèse **32 Mo** : images des publications sociales, deux fichiers
Scribe et — important — les **deux clés des licences hors-ligne**
(`private/offline_private.key`, `offline_public.key`). Un cron `schedule:run` chaque minute
(`deployments:advance`, `instances:check`, publication sociale, expiration des abonnements),
un worker `queue:work` sous supervisor. Courrier par l'API Mailgun (HTTPS, donc insensible au
blocage SMTP de Scaleway). Stripe envoie ses webhooks à `ghosteo.eu` : ils suivront le DNS
et Stripe réessaie de lui-même en cas de 503. Pas de relais Gemini configuré.

**DNS** : la zone `ghosteo.eu` reste chez OVH (elle porte le courrier). `@` et `www` sont des
A vers `51.178.87.41` avec un **TTL de 3 600 s**, et **il existe un AAAA** vers l'IPv6 du VPS
(`2001:41d0:404:200::9036`). control-01 n'a pas d'IPv6 publique : cet AAAA doit être
**supprimé** avant la bascule, sinon les visiteurs en IPv6 resteraient sur l'ancien serveur.
`panel.ghosteo.eu` pointe déjà vers control-01. Aucun changement de serveurs de noms, donc
DNSSEC n'entre pas en jeu.

**Les instances** : les 8 `.env` de worker-01 portent `LICENSE_SERVER_URL=https://ghosteo.eu`.
L'instance appelle `POST /api/v1/licenses/verify` quand son cache expire (12 h si la licence
est active, 5 min sinon) ; le serveur inscrit `licenses.last_verified_at`. C'est la preuve à
lire après bascule, et l'on peut forcer la revalidation en vidant le cache de chaque instance.

**Place sur control-01** : 2,2 Go disponibles sur 3,9, disque à 40 %, l'image `mysql:8.4`
déjà en cache. Le back-office (~150 Mo) et sa base (~300 Mo) tiennent.

#### Le plan, en cinq temps

| # | Quoi | Qui | Coupure |
|---|---|---|---|
| A | **Image Docker du back-office** : `Dockerfile` calqué sur celui de `ghosteo` (PHP 8.3, nginx + php-fpm, trois rôles web/scheduler/queue), workflow qui construit à chaque fusion sur `main` et publie `ghcr.io/guim31/ghosteoeu-main:<sha>` en privé, et `trustProxies` dans `bootstrap/app.php` (absent aujourd'hui : derrière Traefik, sans lui, tout serait généré en `http://` — le bug déjà corrigé sur `ghosteo` par la PR 194). PR à fusionner par Guilhem, qui remet temporairement la permission « Workflows » sur son jeton, puis la retire. | moi, puis Guilhem | aucune |
| B | **Répétition à blanc sur control-01** : service MySQL 8.4 créé par Dokploy (`mysql.create`), service compose `backoffice` depuis l'image, restauration de la sauvegarde nocturne chiffrée (déchiffrée sur control-01, jamais sur le Beelink), copie de `storage/app`, `.env` adapté (`DB_HOST` = le conteneur MySQL, `TRUSTED_PROXIES=*`, journaux sur stderr, `APP_KEY` **inchangée** : elle chiffre les jetons Dokploy, DNS et métriques et les `.env` des déploiements). Vérification en visant l'adresse (`curl --resolve`), pas de domaine déclaré. | moi | aucune |
| C | **La veille** : chez OVH, TTL de `ghosteo.eu` et `www.ghosteo.eu` à 60 s, suppression de l'AAAA. | Guilhem | aucune |
| D | **La bascule, un soir, ~10 min ensemble** : maintenance sur le VPS → dump à froid → restauration → copie finale de `storage/app` → **Guilhem change les deux A vers `51.158.96.49`** → 90 s → domaines `ghosteo.eu` et `www` déclarés dans Dokploy (jamais avant, leçon de la phase 5) → certificat → contrôles par `--resolve`. Retour arrière : remettre les deux A, sortir le VPS de maintenance. | ensemble | 5 à 10 min, invisible des instances (cache 12 h) |
| E | **Licences** : revalidation forcée des 8 instances (cache vidé, une requête), lecture de `last_verified_at` dans la base du back-office, puis moniteur : les blocs de métriques s'allument en renseignant `172.31.40.2` / `172.31.40.3`. | moi | aucune |

**Pourquoi MySQL et pas SQLite ici** : la base est minuscule, le dump se restaure en quelques
secondes sans conversion, et Dokploy sait planifier ses sauvegardes vers un stockage S3.
Le choix SQLite valait pour multiplier des instances ; il n'y en a qu'une.

**Pourquoi une image construite par GitHub et pas un build sur control-01** : même geste que
pour les instances (mettre à jour = changer le tag), aucune compilation sur le serveur de
contrôle, et le dépôt reste privé. Coût : ~5 min d'Actions par fusion sur `main`.

**Ce qui reste à concevoir** (rien n'existe encore) : le `Dockerfile` et le workflow du
back-office, le gabarit compose `compose/backoffice.yml`, et un petit outil
`migrate-backoffice.py` (sauvegarder / restaurer / maintenance / vérifier / retour-arrière)
qui reprend les briques de `migrate-instance.py` sans sa partie SQLite.

**Préalable à l'extinction du VPS, découvert en préparant** : les 8 instances de worker-01
n'ont **aucune sauvegarde**. La sauvegarde nocturne (`backup-vps.sh`) ne connaît que le VPS,
dont les copies sont figées depuis les bascules. Tant que le VPS existe il reste une copie
d'il y a quelques jours ; **une fois éteint, les dossiers patients n'existeraient qu'à un
seul endroit**. Une sauvegarde nocturne de worker-01 (volumes SQLite + documents) et de la
base du back-office sur control-01 doit exister **avant** de résilier. À inscrire dans
l'étape 4.

**Secrets brûlés à ce jour, pour l'étape 5** : clé Scaleway `beelink-migration`, jeton API
Dokploy, jeton de l'agent de métriques, clé Scaleway `backoffice-dns` (posée par tinker),
et — depuis ce matin — le **secret de webhook Stripe** du back-office, affiché par erreur en
lisant le `.env` du VPS (à régénérer dans le tableau de bord Stripe, puis à saisir dans les
variables du service). La clé d'`anais-delaunay` reste un risque accepté (12/09).

**Dates** : renouvellement du VPS OVH le **23/09/2026**, à prendre **sans engagement** ;
les anciennes instances sont à conserver jusqu'au **13/10/2026** (30 jours après la dernière
bascule). La résiliation ne devrait donc pas précéder le 13/10.

#### Étape A faite le 13/09/2026 : l'image du back-office — PR https://github.com/guim31/ghosteoeu-main/pull/64

`Dockerfile` multi-étapes calqué sur celui de `ghosteo` (assets Vite en Node 22 comme la CI
de ce dépôt, dépendances Composer, image finale `serversideup/php:8.3-fpm-nginx`),
`.dockerignore`, entrée `docker/entrypoint.d/`, workflow `docker.yml` et `trustProxies`.

**Le workflow diffère de celui de `ghosteo` sur un point** : ce dépôt n'a pas de versions
taguées, sa livraison est la fusion d'une PR dans `main`. C'est donc la fusion qui construit
l'image, avec deux tags — `main-<sha court>` pour désigner un commit précis (le retour
arrière) et `latest`. Le piège du tag posé par le `GITHUB_TOKEN` (12/09) ne se pose pas ici.

Contrôles avant d'ouvrir la PR, sur le banc du NAS : Pint 292 fichiers, PHPStan sans erreur,
**423 tests**. Image construite (**841 Mo**) et démarrée contre un MySQL 8.4 jetable :
migrations jouées, `/up`, `/login` et `/mentions-legales` à 200, assets Vite servis, lien
`public/storage` posé, `gd` **avec FreeType** (le titre des visuels sociaux est réellement
dessiné avec la police Outfit — testé, pas seulement listé), `intl`, `bcmath`, `pdo_mysql`
présents, et **les trois rôles démarrent depuis la même image**, le planificateur exécutant
bien `deployments:advance` à la minute.

**Trois choses apprises en construisant, qui valent pour les deux dépôts :**

1. **`bootstrap/cache/*` doit être exclu de l'image.** Un build lancé depuis un poste de
   travail y trouve les fournisseurs de développement déjà découverts (Laravel Pail),
   absents de l'image construite sans les dépendances de développement : `package:discover`
   s'arrête sur une classe introuvable et le build échoue. La CI part d'un dépôt propre et
   ne le voit jamais. *Le `.dockerignore` de `ghosteo` a le même trou* — sans conséquence
   tant que ses images sont construites par GitHub, à corriger à l'occasion.
2. **`trustProxies` manquait bel et bien**, et la preuve est nette : avec l'en-tête de proxy,
   les 16 URL de la page de connexion sortent en `https` ; sans lui, en `http`. Déployer
   sans ce correctif aurait donné un site sans feuille de style, comme le staging en phase 2.
3. **Le conteneur n'attend la base que 30 secondes** au démarrage (comportement de
   `serversideup/php`). Si la base démarre en même temps que lui — cas d'un premier
   déploiement — il s'arrête avant qu'elle soit prête. Le `restart: unless-stopped` le
   rattrape, mais le gabarit compose pose en plus une condition d'état de santé.

Le jeton GitHub ne peut pas lire l'état des vérifications d'une PR (403, permission
« Checks » non accordée, cohérent avec le périmètre choisi) : la CI se regarde sur la page
de la PR. La réplique locale du NAS est identique à `tests.yml` et elle est verte.

**Reste à faire par Guilhem pour clore l'étape A** : fusionner la PR #64 — la fusion
construit et publie l'image toute seule — puis retirer la permission « Workflows » du jeton.

#### Étape B préparée le 13/09/2026 : le gabarit et l'outil de bascule

`compose/backoffice.yml` et `scripts/migrate-backoffice.py`, écrits mais **pas encore
lancés** : ils attendent que l'image existe, donc la fusion de la PR #64.

**Le gabarit compose porte quatre conteneurs** et non trois : les rôles `web`, `scheduler`
et `queue` depuis l'image, plus `db` en `mysql:8.4`, la version de l'ancien serveur. La
base reste MySQL — 7,7 Mo, le dump se restaure tel quel sans conversion, et il n'y en a
qu'une : le choix SQLite servait à multiplier les instances.

**L'outil reprend les leçons de la phase 5** et en ajoute trois propres au back-office :

1. **La zone `ghosteo.eu` est chez OVH, pas chez Scaleway.** Aucune API : la bascule
   s'arrête et dicte à Guilhem les trois lignes à changer, puis la commande `dns` reprend.
   Elle vérifie l'autorité OVH **et** trois résolveurs publics avant de déclarer quoi que
   ce soit, attend 90 s, puis pose les domaines — jamais avant, leçon du quota ACME.
2. **Deux planificateurs ne doivent jamais tourner ensemble.** Celui du back-office fait
   avancer les déploiements et sonde les instances chaque minute. Pendant la répétition,
   les conteneurs `scheduler` et `queue` de la copie sont donc **arrêtés** (`unless-stopped`
   respecte un arrêt manuel) ; côté VPS, c'est le mode maintenance qui les endort — Laravel
   n'exécute ni les tâches planifiées ni la file d'attente quand l'application est « down ».
   C'est aussi ce qui fige les comptes entre la sauvegarde et le contrôle.
3. **Le contrôle de conformité est souple à la répétition, strict à la bascule.**
   `instance_checks` compte **55 734 lignes** et grossit toutes les cinq minutes : exiger
   l'égalité sur une source en service ferait échouer la répétition à coup sûr. Les tables
   du métier (`users`, `licenses`, `instances`, `settings`, `plans`, `servers`,
   `subscriptions`, `site_deployments`…) doivent en revanche correspondre exactement, dans
   les deux cas. Comptage de référence relevé sur le VPS le 13/09 : **30 tables,
   59 562 lignes**, dont 11 comptes, 10 licences, 10 instances, 40 réglages.

**Deux précautions reprises telles quelles** : les mots de passe ne passent jamais en
argument — le shell **du conteneur** MySQL lit la variable que Docker y a déjà, donc rien
n'apparaît dans un `ps` (incident du 12/09) — et l'identifiant du propriétaire des fichiers
est **lu dans le conteneur** avant de l'arrêter, jamais supposé.

**Le point le plus délicat, et la raison pour laquelle `APP_KEY` est conservée telle
quelle** : elle ne chiffre pas des dossiers patients ici, mais les **réglages en base** —
jeton de l'API Dokploy, jeton DNS Scaleway, jeton de l'agent de métriques — et les `.env`
des déploiements. La changer rendrait le back-office incapable de piloter quoi que ce soit.

**Ce que la bascule ne changera pas** : les huit instances portent
`LICENSE_SERVER_URL=https://ghosteo.eu` et suivent donc le DNS sans aucune modification.
Stripe et Mailgun aussi ; Stripe réémet ses webhooks en cas d'échec.

#### Point d'arrêt du 13/09/2026 : la PR #64 attend Guilhem

Au 13/09 à 10h10, la PR #64 est **ouverte, fusionnable, mais GitHub la dit `UNSTABLE`** :
une vérification n'y est pas au vert — en cours, en attente, ou en échec, impossible de le
savoir d'ici. Le jeton GitHub n'a ni « Checks » ni « Actions » en lecture (403 sur
`/commits/<sha>/check-runs`, sur `/actions/runs` et sur l'API des paquets). C'est cohérent
avec le périmètre choisi le 27/08/2026, et ce n'est pas à corriger pour si peu.

**Les trois commandes de `tests.yml` ont été rejouées à l'identique sur le banc du NAS, et
les trois passent**, y compris avec un `.env` neuf recopié depuis le `.env.example`
modifié — c'était la seule différence non couverte par la première vérification :

| Étape de la CI | Résultat sur le banc |
|---|---|
| `php artisan test` (SQLite en mémoire) | 423 tests, 1 149 assertions |
| `vendor/bin/pint --test -v` | 292 fichiers |
| `vendor/bin/phpstan analyse --memory-limit=2G` | aucune erreur |
| `npm ci && npm run build` (Node 22) | 6 fichiers produits, 13 s |

Les deux fichiers de workflow sont par ailleurs du YAML valide.

**À regarder par Guilhem sur la page de la PR** : si la vérification est simplement en
cours, il n'y a rien à faire ; si elle est en échec, le message dira quoi. Une piste à
écarter en premier, vu l'historique : le **budget GitHub Actions**, épuisé en août 2026,
et sollicité toute la semaine par les images de `ghosteo`.

#### Vérifications à blanc de l'outil, faites le 13/09/2026

Les parties en lecture seule tournent déjà correctement :

- **État DNS** : les quatre sondes (autorité OVH + Google, Cloudflare, Quad9) répondent
  `51.178.87.41` pour `ghosteo.eu` et `www`, et l'**AAAA `2001:41d0:404:200::9036` est bien
  là**. L'outil conclut « pas prêt à déclarer les domaines », ce qui est la bonne réponse.
- **Découverte des instances** : les huit sont trouvées sur worker-01 avec leur nom de
  service, ce qui alimentera la commande `licences`.

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
