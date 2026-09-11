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
