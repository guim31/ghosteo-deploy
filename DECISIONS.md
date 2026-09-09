# GHosteo — choix d'architecture de déploiement

État des lieux et recommandations du 09/09/2026, rédigés avant toute mise en œuvre.
Ce document tranche les questions techniques ; les questions qui relèvent de Guilhem
sont listées en fin de document et bloquent une partie du plan.

---

## Résumé

1. **Ne pas construire « GHosteoPloy » en Node.** L'orchestrateur existe déjà, en PHP,
   dans `ghosteoeu-main` : machine à étapes idempotente, `.env` chiffré en base,
   cascade de mises à jour, moniteur d'instances. Le concept Node a été écrit avant, il
   ferait doublon avec deux bases de secrets et deux vérités. Ce dépôt (`ghosteo-deploy`)
   devient le dépôt d'**infrastructure** : cloud-init, gabarits, documentation. Pas une
   application.
2. **Le verrou n'est pas l'orchestrateur, c'est le build sur le serveur.** Aujourd'hui
   chaque instance cliente refait `composer install` + `npm ci` + `npm run build` à chaque
   déploiement, sur le serveur de production, l'une après l'autre. Packager GHosteo en
   **image Docker construite par la CI au tag** transforme un déploiement en
   « tirer l'image, migrer, redémarrer ». C'est ce qui rend 15 instances triviales, et
   c'est un geste déjà maîtrisé (Musicarr, iptv_webplayer sur ghcr.io).
3. **Couche d'exécution : Dokploy auto-hébergé**, un panneau sur un petit VPS de
   contrôle, N serveurs « workers » attachés en SSH. Un client = une application depuis
   l'image + une base + un domaine. Traefik fait le TLS, Dokploy planifie les
   sauvegardes de base vers un stockage S3.
4. **L'orchestrateur de `ghosteoeu-main` pilote Dokploy** à la place de Vito : même
   machine à étapes, un `DokployClient` à la place de `VitoDeploymentClient`, une table
   `servers` avec capacité. Ajouter un serveur devient un script (`cloud-init` + un appel
   API Dokploy), pas une après-midi.
5. **Séparer les plans** : le serveur de licences, la démo et le staging quittent le
   serveur des clients. Un incident de charge chez un client ne doit plus toucher le
   service dont toutes les instances dépendent.
6. **HDS est une décision juridique et commerciale, pas un choix de VPS.** À trancher
   avant de signer chez un fournisseur (voir § 6). L'architecture proposée fonctionne
   dans les deux cas.

---

## 1. Ce qui existe déjà

### Dans `ghosteoeu-main`

`App\Services\Deployment\SiteDeploymentRunner` déroule dix étapes, une par « tick »
(poll de la page ou planificateur), avec verrou, reprise après échec et tolérance au
« existe déjà » :

```
base → utilisateur MySQL → site Vito → attente install → .env → script de déploiement
→ SSL → déploiement → attente build → inscription au moniteur
```

- `EnvFileGenerator` rend le `.env` depuis un gabarit, tire `APP_KEY` et le mot de passe
  MySQL, et **le `.env` est stocké chiffré** dans `site_deployments.env`. C'est
  important : `APP_KEY` chiffre les dossiers patients, sa perte rend les données
  illisibles. Ce point est déjà couvert et doit le rester.
- `InstanceUpdateRunner` redéploie site par site, jamais deux builds en parallèle,
  40 min de délai par site.
- Le moniteur (`InstanceCheckService`, `UptimeService`, `VersionService`) sonde chaque
  instance, vérifie l'identité de l'hôte, le TLS, le DNS, et lit la version applicative
  remontée par le ping de licence.
- `VitoDeployService` lit les métriques serveur de Vito, avec un diagnostic
  (`instances:vito-doctor`) parce que l'endpoint varie selon la version de Vito.

Autrement dit, le « wizard zéro saisie » du concept GHosteoPloy **existe déjà** pour
l'étape « ajouter un client sur un serveur connu ». Ce qui manque :

- **ajouter un serveur** (Vito n'a pas de fournisseur OVH : serveur « custom », clé SSH,
  installation à la main) ;
- **déployer sans construire** sur chaque serveur ;
- **répartir** les clients sur plusieurs serveurs selon la capacité.

### Dans `ghosteo`

- Laravel 12, PHP 8.2 minimum, MySQL en production, SQLite en tests, CI et desktop.
- Aucun `Dockerfile`. Le déploiement est `scripts/deploy.sh` (git reset, composer, npm,
  migrate, optimize, reload PHP-FPM), exécuté par Vito sur chaque site.
- État hors code : la base ; `storage/app/{patient_files,factures,backups,public}` ;
  `storage/app/hardware_id` ; le `.env`.
- Aucune requête SQL brute dans `app/` (`DB::raw`, `whereRaw`, `selectRaw` : zéro
  occurrence). Le code est donc portable entre moteurs.
- `BackupService` produit un zip (dump + fichiers + manifeste) et `InstallController`
  le restaure sur une instance vierge avec remappage des praticiens. **C'est l'outil de
  migration** ; il n'y a rien à écrire de plus pour déplacer une instance.
- `scripts/deploy.sh` contient un appel `gemini:check` et `deploy:notify` qui
  appartiennent au dépôt `ghosteoeu-main`, pas à `ghosteo` : à trier au moment de
  containeriser.

### Les douleurs mesurables du flux actuel

| Douleur | Cause | Effet |
|---|---|---|
| Un serveur en plus = une après-midi | Vito sans fournisseur OVH ; provisionnement manuel | non reproductible, dépend de la mémoire de Guilhem |
| Mise à jour lente et coûteuse en CPU | composer + npm + build **par site**, séquentiel | 6 sites = 6 builds ; 40 min de délai par site ; le CPU du serveur des clients est mobilisé pendant leurs heures d'ouverture |
| Tout sur un serveur | licences + démo + staging + clients | un client qui sature touche le serveur de licences, donc toutes les instances |
| Recette sur le même serveur que la production | staging à côté des clients | un test de charge ou de restauration concurrence les cabinets |

---

## 2. Décision 1 : GHosteo devient une image Docker

C'est le pivot ; tout le reste en découle et rien de ce qui suit n'a de sens sans elle.

### Contenu

- **Multi-stage** : `node:20-alpine` construit `public/build` ; `composer` installe
  `vendor` sans dev ; image finale sur une base PHP-FPM + nginx maintenue pour Laravel
  (par exemple `serversideup/php:8.3-fpm-nginx`, qui gère déjà les permissions, le
  healthcheck, `schedule:work` et `queue:work` depuis la même image).
- **Une image, trois rôles** : `web` (fpm + nginx), `scheduler` (`php artisan
  schedule:work`), `queue` (`php artisan queue:work database`). Le cron Vito disparaît.
- **Migrations au démarrage** de `web` (`php artisan migrate --force`), `optimize` au
  build. Le déploiement d'une version se réduit à changer le tag.
- **État en volume** : `storage/app` monté sur un volume nommé ; la base est à part ;
  le `.env` devient des variables d'environnement du conteneur. Jamais d'état dans le
  conteneur.
- **Tag = version** : `ghcr.io/guim31/ghosteo:1.16.0`, produit par un workflow déclenché
  par le tag `v*` que `release.yml` pose déjà. Le retour arrière est le tag précédent.
- **Image privée** : elle contient le code PHP de GHosteo, dépôt privé. Contrairement à
  Musicarr, le package ghcr **ne doit pas être public**. Dokploy centralise les
  identifiants de registre (un jeton `read:packages` dédié), les workers n'en stockent
  aucun.

### Points d'attention

- **Budget GitHub Actions** : les 2 000 minutes ont été épuisées en août 2026. Un build
  d'image Laravel coûte 4 à 6 minutes avec le cache Buildx. Le déclencher **uniquement au
  tag**, jamais sur `develop`. Staging tire l'image `:develop` seulement si un tag de
  pré-version est posé à la main.
- **`deploy.sh` disparaît pour le SaaS.** Il reste utile pour une installation hors
  Docker (client qui héberge lui-même), à documenter comme tel.
- **NativePHP** n'est pas concerné : `build.yml` continue de produire les binaires.
- **`hardware_id`** : le fichier vit dans le volume, il survit donc aux redéploiements.
  Le vérifier lors du premier test, sinon chaque redéploiement déclenchera
  `hardware_mismatch` côté licence.

---

## 3. Décision 2 : l'orchestrateur reste dans `ghosteoeu-main`

### Pourquoi

- La donnée métier y est : licence, client, plan, domaine autorisé, historique.
- Les secrets y sont déjà chiffrés au repos (`Setting`, `site_deployments.env`).
- Le modèle « un appel d'API par tick, aucun processus long » y est éprouvé, et il
  convient exactement à une API HTTP comme celle de Dokploy.
- Le moniteur y lit déjà la version, le TLS, le DNS et l'identité de chaque instance.
- Un second panneau en Node dupliquerait tout ça, avec un `.env` de secrets non chiffré
  et une UI de plus à maintenir.

### Ce qui change

- Une **interface `DeploymentBackend`** (créer base, créer app, pousser env, domaine,
  déployer, état) avec deux implémentations le temps de la migration : `VitoBackend`
  (l'existant, renommé) et `DokployBackend`. Vito est retiré quand le dernier site a
  migré.
- Un modèle **`Server`** : fournisseur, identifiant, IP, identifiant Dokploy, RAM,
  plafond d'instances, statut. Le wizard choisit le serveur qui a de la place ; la
  capacité est d'abord un **compteur avec plafond** (6 par serveur comme aujourd'hui),
  pas une lecture de métriques. C'est moins beau et beaucoup plus fiable ; les métriques
  restent une alerte, pas un critère d'affectation.
- Les étapes deviennent : **DNS → base → application (image) → variables → domaine
  (TLS par Traefik) → déploiement → attente → inscription au moniteur**. Deux étapes de
  moins qu'aujourd'hui (plus de script de déploiement, plus d'utilisateur MySQL à lier).
- `InstanceUpdateRunner` devient « changer le tag d'image et redéployer ». Un
  redéploiement dure le temps d'un `docker pull`, donc la cascade peut se faire pendant
  la nuit sans réveiller personne, et le retour arrière est un tag.
- **Une étape DNS** apparaît : un enregistrement `A` par client, via l'API du
  registrar du domaine. Avec plusieurs serveurs, le wildcard `*.ghosteoapp.eu` ne
  suffit plus, sauf à mettre un reverse proxy unique devant tous les workers, ce qui
  recréerait un point de panne unique. Un `A` par client est la bonne réponse.

### Topologie cible

```
Plan de contrôle (1 VPS, 2 vCPU / 4 Go)          Plan clients (N VPS « workers »)
┌──────────────────────────────────────┐          ┌──────────────────────────────┐
│ Dokploy (panneau, Traefik, Postgres)  │──SSH────▶│ worker-01 : Docker + Traefik │
│ ghosteo.eu  (licences, back-office)   │          │   client-a  (web/sched/queue)│
│ demo.ghosteo.eu                       │──SSH────▶│   client-a-db (MariaDB)      │
│ staging.ghosteoapp.eu                 │          │   client-b … ×6              │
└──────────────────────────────────────┘          ├──────────────────────────────┤
        ▲ API HTTP (tick)                          │ worker-02 : …                │
        └── ghosteo.eu pilote Dokploy              └──────────────────────────────┘
                                                            │ sauvegardes S3 (même
                                                            ▼ périmètre HDS si HDS)
```

Le plan de contrôle **n'est pas à la maison**. Le concept initial proposait le NAS :
c'est une chaîne d'administration sur un accès domestique, incompatible avec l'activité 5
du référentiel HDS si cette voie est retenue, et fragile dans tous les cas. Si le panneau
tombe, les instances continuent de tourner : Docker et Traefik ne dépendent pas de lui.

---

## 4. Décision 3 : Dokploy comme couche d'exécution

### Ce qu'il apporte, et qui serait à réécrire sinon

- Serveurs distants attachés en SSH, chacun autonome avec son Traefik et ses conteneurs.
- Applications depuis une image de registre privé, variables d'environnement, volumes,
  domaines avec certificat Let's Encrypt automatique.
- Bases MySQL/MariaDB/Postgres en conteneur, avec **sauvegardes planifiées vers S3**.
- Journaux, terminal, monitoring et redémarrage par conteneur depuis le panneau, sans SSH
  à la main.
- API HTTP avec clé, et CLI.

### Ce qu'il coûte

- **Une API jeune.** Épingler la version de Dokploy, la monter d'abord sur le plan de
  contrôle avec staging, et n'en utiliser qu'une dizaine d'appels, tous isolés dans
  `DokployClient`. La machine à étapes tolère déjà les réponses variables de Vito ; le
  même soin s'applique ici.
- **Une base par client = un conteneur MariaDB par client**, soit 200 à 400 Mo de RAM
  chacun. Sur un worker de 8 Go, six clients tiennent largement (6 × (150 Mo d'app +
  250 Mo de base) ≈ 2,5 Go). Le plafond de 6 se révise avec la RAM réelle du worker.
- Le panneau SSH vers les workers : si le VPS de contrôle est compromis, tous les
  workers le sont. Clé SSH dédiée, pare-feu des workers restreint à l'IP du panneau,
  2FA sur le panneau.

### Alternatives écartées, et pourquoi

| Option | Verdict |
|---|---|
| **Garder Vito** et lui ajouter des serveurs | Vito construit sur le serveur ; pas de fournisseur OVH ; c'est le flux actuel avec plus de machines. |
| **Coolify** | Équivalent fonctionnel de Dokploy. Le choix Dokploy est déjà fait, pas de raison de le rouvrir. |
| **Compose + SSH maison** | Zéro dépendance, mais TLS, sauvegardes, journaux et UI à réécrire, et SSH depuis PHP par ticks est plus lourd que HTTP. À reconsidérer seulement si l'API Dokploy déçoit. |
| **Kubernetes managé** (Kapsule, OVH MKS) | La réponse « textbook » à un SaaS mono-instance par client, mais trop lourd pour une personne seule qui doit vendre. L'image Docker garde cette porte ouverte : un chart Helm par client se fait plus tard sans rien changer à l'application. |
| **Multi-tenant** (une instance, N cabinets) | Réécriture profonde de GHosteo ; l'isolation par instance est aussi un argument commercial et RGPD. Non. |

---

## 5. Décision 4 : un serveur se crée par un script, pas dans une UI

Ajouter un worker arrive quelques fois par an. Ce geste **n'a pas besoin d'un wizard** ;
il a besoin d'être reproductible en dix minutes sans réfléchir.

1. `terraform apply` (ou un script `create-worker.sh` sur l'API du fournisseur) crée
   l'instance avec un **cloud-init** versionné ici : Docker, `ufw` (22 depuis l'IP du
   panneau, 80/443 ouverts), `fail2ban`, `unattended-upgrades`, clé SSH du panneau.
2. Un appel à l'API Dokploy attache le serveur et lance son installation.
3. Une ligne dans la table `servers` de `ghosteoeu-main`, avec son plafond.

Ce dépôt garde : `cloud-init/worker.yaml`, `terraform/` (ou le script), le gabarit des
variables d'environnement client, et cette documentation. Aucun secret, le dépôt est
public.

---

## 6. HDS : à trancher avant de choisir le fournisseur

Ce point est **hors de mon périmètre de décision** et conditionne le fournisseur, le
niveau de support, le contrat et le lieu des sauvegardes. Résumé factuel, à valider avec
un juriste :

- L'hébergement de données de santé pour le compte d'un tiers est une obligation légale
  (art. L.1111-8 du Code de la santé publique), pas un label. Un éditeur SaaS qui
  héberge les dossiers patients de ses clients est un « hébergeur » au sens du texte :
  il doit lui-même être certifié pour les activités 5 et 6 en s'appuyant sur un
  fournisseur certifié pour les activités 1 à 4. Prendre un VPS « HDS » ne suffit pas.
- L'applicabilité à l'ostéopathie est la vraie question : l'ostéopathe n'est pas
  « professionnel de santé » au sens du CSP, mais les données recueillies sont des
  données de santé (RGPD art. 9) et l'activité est une activité de soins. C'est une
  question de juriste, pas d'architecture.
- OVHcloud certifie ses **Public Cloud Instances** (option HDS à activer, support
  Business ou Enterprise obligatoire). Scaleway est certifiée activités 1 à 4 sur
  Instances, Block/Object Storage, Bare Metal et VPC, avec contrat HDS et support
  minimal. Dans les deux cas, **seuls les produits listés au contrat** sont couverts.
- Conséquence pratique immédiate, HDS ou pas : **les sauvegardes des clients ne vont pas
  sur le NAS de la maison.** Object Storage chez le fournisseur, chiffré, dans le même
  périmètre contractuel que les instances.

Tant que la question n'est pas tranchée : ne pas écrire « HDS » sur ghosteo.eu, et
choisir un fournisseur dont l'offre HDS existe pour ne pas avoir à re-migrer. L'image
Docker et Dokploy fonctionnent à l'identique chez OVHcloud et Scaleway.

---

### 6 bis. Ce que coûte réellement « HDS » (complément du 09/09/2026)

Les abonnements GHosteo sont à 9 € (Essentiel) et 19 € (Pro) par mois. Le chiffre qui
compte n'est donc pas le prix d'un serveur, c'est le **coût d'hébergement par client**.

| Voie | Ce que ça implique | Coût plancher |
|---|---|---|
| OVHcloud Public Cloud HDS | option HDS + support Business ou Enterprise obligatoire | plusieurs centaines d'euros par mois de support avant le premier serveur |
| Scaleway HDS | contrat HDS signé avec les ventes + support Business (250 € HT/mois ou 10 % de la facture) | ≈ 250 €/mois avant le premier serveur |
| Scalingo (PaaS, certifié activités 1 à 6) | région `osc-secnum-fr1` sur demande, tarif non public, supérieur au standard (conteneur S à 14,40 € + base MySQL) | ≈ 25 à 40 € **par client** |
| Clever Cloud (PaaS, certifié 1 à 6 depuis 01/2025) | 200 €/mois fixes + résultats ×1,4 sur les ressources | ≈ 200 €/mois + 1,4 × ressources |

Avec 15 clients, le chiffre d'affaires est d'environ 200 €/mois : chaque voie HDS coûte
autant ou plus que ce qu'elle héberge. Aucun fournisseur ne certifie l'éditeur à sa
place (Clever Cloud l'écrit noir sur blanc). Le seuil de bascule raisonnable est autour
de 40 à 50 clients, ou une ligne tarifaire dédiée.

**Décision** : Scaleway Instances dès maintenant, sur les produits couverts par leur
certification (Instances, Block Storage, Object Storage), **sans** contrat HDS, avec
Docker + Dokploy comme prévu. Le contrat HDS et le support Business se signent plus
tard comme un avenant, sans re-migrer. En attendant, **retirer la mention HDS de
ghosteo.eu** : le VPS actuel n'est pas couvert, et la formulation de remplacement doit
être validée par un juriste.

Les PaaS (Scalingo, Clever Cloud) imposent aussi un système de fichiers éphémère : les
documents patients devraient passer sur un stockage objet, ce qui est un changement dans
GHosteo. À reconsidérer seulement au-delà du seuil ci-dessus.

## 7. Questions ouvertes pour Guilhem

1. **HDS** : oui, non, ou plus tard ? Change le fournisseur, le support, le contrat.
2. **Fournisseur** : tranché le 09/09/2026, **Scaleway** (voir § 6 bis). Le support
   exigé pour HDS y est dix fois moins cher que chez OVHcloud, l'API est un REST classique
   avec jeton et fournisseur Terraform, et l'hébergement DNS est inclus.
3. **Base par client** : tranché le 09/09/2026, **SQLite dans le volume de l'instance**,
   sous réserve d'une validation sur staging. Motifs : deux ou trois praticiens par
   cabinet, aucune requête SQL brute dans le code, suite de tests et version desktop déjà
   sur SQLite, zéro conteneur de base donc trois fois plus de clients par serveur,
   sauvegarde et migration réduites à une copie de fichier. Conditions : mode WAL,
   restauration d'une sauvegarde MySQL anonymisée vers SQLite (prévoir une commande
   artisan de copie table par table si le dump SQL ne passe pas), une semaine de staging.
   Repli si un blocage apparaît : MariaDB en conteneur par client via Dokploy.
4. **DNS** : constaté le 09/09/2026, les zones `ghosteo.eu` et `ghosteoapp.eu` sont
   hébergées chez OVH (`ns100.ovh.net`, `ns10.ovh.net`) avec un **joker** : n'importe
   quel sous-domaine, même inexistant, répond `51.178.87.41`. Avec plusieurs serveurs ce
   joker disparaît et chaque client reçoit sa ligne, créée par le back-office. Décision :
   déplacer l'hébergement des zones (pas les noms, qui restent achetés chez OVH) vers
   Scaleway Domains & DNS au moment du premier serveur Scaleway, pour n'avoir qu'un seul
   jeton d'API. C'est un changement de serveurs de noms chez OVH, fait une fois.
5. **Le VPS OVH actuel** : le garder comme VPS de contrôle une fois Vito retiré, ou
   repartir sur une instance neuve ? Repartir propre est plus simple que nettoyer.

---

## 8. Plan de migration, dans l'ordre

Chaque étape laisse la production intacte et se valide seule.

| # | Étape | Où | Effort indicatif |
|---|---|---|---|
| 1 | `Dockerfile` multi-stage + `docker.yml` (build au tag) + test local sur des données anonymisées | `ghosteo` | 1 à 2 jours |
| 2 | VPS de contrôle : Dokploy, staging depuis l'image, cycle « nouveau tag → redéploiement » validé | infra | ½ journée |
| 3 | `DokployClient`, `Server`, `DeploymentBackend`, étapes adaptées, DNS ; déployer un client de test | `ghosteoeu-main` | 3 à 5 jours |
| 4 | Basculer ghosteo.eu et la démo sur le VPS de contrôle | infra | ½ journée |
| 5 | Premier worker par cloud-init ; migrer les clients un par un : sauvegarde → nouvelle instance → restauration par l'assistant d'installation → bascule DNS (TTL abaissé la veille) | infra + back-office | 1 jour, puis ~1 h par client |
| 6 | Retirer `VitoBackend` et le VPS Vito | tout | ½ journée |

Vito reste actif jusqu'à l'étape 6 : il n'y a pas de bascule brutale, et chaque client
migre à son heure.
