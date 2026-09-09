# GHosteo — guide pas à pas de la migration

Ce guide s'adresse à Guilhem. Il dit, phase par phase, **ce que tu fais**, **ce que je
fais**, et **ce que tes clients voient**. Les choix techniques sont dans `DECISIONS.md` ;
ici, seulement les gestes.

Trois principes qui doivent te rassurer, parce qu'ils sont vrais à chaque étape :

1. **Rien ne touche un client avant la phase 5**, et à ce moment-là tout aura été répété
   sur des instances de test.
2. **L'ancien serveur reste allumé et intact jusqu'à la fin.** Un client migré peut
   revenir en arrière en quelques minutes, par un simple changement d'adresse.
3. **Aucune phase ne commence sans ton feu vert**, et chaque phase se termine par une
   vérification que tu peux faire toi-même dans un navigateur.

---

## 0. Comment on travaille ensemble

### Où se passe le travail

Tout se fait **depuis cet agent, sur le Beelink** (l'ordinateur de la maison que tu
pilotes par Remote Control). C'est la seule machine qui a les clés SSH, le compte GitHub
et la connexion réseau nécessaires. Les sessions Claude Code « cloud » ne conviennent
pas : elles ne peuvent ni installer les dépendances PHP ni se connecter aux serveurs.

### Une conversation par phase

Cette conversation n'a pas à tout porter. Le contexte se résume automatiquement quand
il grossit, mais **une conversation neuve par phase est plus propre et plus sûre**. Deux
fichiers font la mémoire entre les conversations :

- `~/homelab/ghosteo-deploy/DECISIONS.md` : les choix.
- `~/homelab/ghosteo-deploy/SUIVI.md` : l'avancement, que je tiens à jour à chaque étape.

Pour ouvrir une nouvelle phase, tu écris simplement :

> Lis `~/homelab/ghosteo-deploy/DECISIONS.md` et `SUIVI.md`, puis démarre la phase N
> du `GUIDE-PAS-A-PAS.md`.

### Les secrets

Trois règles, pour que le moins de mots de passe possible passent par la conversation :

- **Ce qui a une interface web, tu le saisis toi-même dedans** : compte Dokploy, réglages
  du back-office ghosteo.eu, registre d'images. Je n'ai jamais besoin de ces mots de passe.
- **Ce que je dois utiliser par script** (clé d'API Scaleway, jeton d'API Dokploy), tu me
  le colles une fois dans la conversation ; je l'écris immédiatement dans un fichier
  protégé sur le Beelink, hors de tout dépôt. **À la fin de la migration, on révoque ces
  clés et on en crée de neuves** : ce qui a transité par une conversation est considéré
  comme brûlé.
- **Rien de secret n'entre dans les dépôts Git**, jamais. `ghosteo-deploy` est public.

### Le rythme

Compte **six phases sur quatre à six semaines**, à raison de quelques heures de ton côté
au total. La plupart des étapes qui t'incombent prennent cinq à quinze minutes. Les
seules qui demandent un créneau calme sont les bascules de la phase 5, à faire le soir
ou le week-end, une par une.

---

## Vue d'ensemble

| Phase | Ce qu'on fait | Impact clients | Ton temps |
|---|---|---|---|
| 0 | Comptes et accès | aucun | 45 min |
| 1 | GHosteo devient une image Docker | aucun | 15 min |
| 2 | Serveur de contrôle Scaleway + Dokploy + staging | aucun | 30 min |
| 3 | Le back-office ghosteo.eu sait déployer sur Dokploy | aucun | 20 min |
| 4 | DNS de `ghosteoapp.eu` chez Scaleway + premier serveur clients + démo | aucun (la démo coupe 10 min) | 30 min |
| 5 | Migration des clients, un par un | 15 à 30 min de coupure **par client**, planifiée | 10 min par client |
| 6 | Bascule de ghosteo.eu, puis extinction de l'ancien serveur | aucun | 15 min |

---

## Phase 0 — Comptes et accès

### 0.1 Compte Scaleway (toi, 20 min)

1. Va sur <https://console.scaleway.com> et crée un compte **au nom de ton entreprise**
   (pas un compte personnel : le contrat HDS, plus tard, se signera sur ce compte).
2. Renseigne le moyen de paiement. Scaleway facture à l'usage, en fin de mois. Ordre de
   grandeur attendu : **un serveur de contrôle et un serveur clients ≈ 40 à 60 € par
   mois** au total, je confirme les prix exacts au moment de créer les machines.
3. Dans le menu **Organisation → Projets**, crée un projet nommé `ghosteo`. Tout ce qu'on
   crée vivra dedans, séparé de tout ce que tu pourrais faire d'autre chez Scaleway.
4. Active la **double authentification** sur ton compte (Organisation → Sécurité).

### 0.2 Clé d'API Scaleway (toi, 5 min)

1. Menu **Organisation → IAM → Clés API → Générer une clé API**.
2. Description : `beelink-migration`. Projet par défaut : `ghosteo`. Expiration : **3 mois**.
3. La console affiche une **Access key** (commence par `SCW…`) et une **Secret key**
   (affichée une seule fois). Colle-les moi toutes les deux dans la conversation.
4. Je les range dans `~/.config/scw/config.yaml` sur le Beelink, protégé, et je vérifie
   aussitôt qu'elles fonctionnent en listant le projet. Tu n'as rien d'autre à faire.

### 0.3 Accès de l'agent à l'ancien serveur OVH (toi, 5 min)

Pour sauvegarder les instances au moment de les migrer, j'ai besoin d'entrer sur le VPS
actuel. VitoDeploy sait ajouter une clé :

1. Dans Vito, ouvre ton serveur → onglet **SSH Keys** → **Add key**.
2. Nom : `beelink-claude`. Clé : celle que je t'afficherai au début de la phase
   (elle commence par `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBwY`, c'est la clé publique
   du Beelink, elle n'a rien de secret).
3. Je vérifie la connexion et je te dis « OK ». Cette clé ne servira qu'à **lire et
   sauvegarder** ; je ne modifierai rien sur l'ancien serveur avant la phase 6.

### 0.4 Permission « Workflows » sur ton jeton GitHub (toi, 5 min)

Je dois ajouter un fichier dans `.github/workflows/` du dépôt `ghosteo` (celui qui
construira l'image). Ton jeton actuel ne l'autorise pas, c'était voulu.

1. GitHub → **Settings → Developer settings → Fine-grained tokens** → ton jeton du
   27/08/2026 → **Edit**.
2. Dans *Repository permissions*, passe **Workflows** à *Read and write*. Enregistre.
3. Tu pourras le remettre à *No access* dès la fin de la phase 1 ; je te le rappellerai.

### 0.5 La mention HDS sur ghosteo.eu (toi, à ton rythme)

Ce point n'est pas technique mais il est urgent : le site annonce le respect du HDS
alors que le VPS actuel n'est pas couvert. Fais valider par un juriste une formulation
de remplacement, par exemple « données hébergées en France, chiffrées, chez un
hébergeur certifié ISO 27001 ». Dis-moi le texte retenu, je fais la modification.

### ✅ Fin de phase 0

Je peux lister ton projet Scaleway, entrer sur le VPS OVH, et écrire un workflow dans
`ghosteo`. Je crée `SUIVI.md` et j'y note ces trois validations.

---

## Phase 1 — GHosteo devient une image Docker

**Impact clients : aucun.** Rien n'est déployé nulle part ; on fabrique seulement un
« paquet » de l'application.

### Ce que je fais

1. J'écris le `Dockerfile` et le workflow `docker.yml` dans le dépôt `ghosteo`, sur une
   branche, et j'ouvre une pull request vers `develop`.
2. Je fais construire l'image sur un serveur de test pour vérifier qu'elle démarre, que
   l'écran d'installation s'affiche, que la sauvegarde/restauration fonctionne et que
   `hardware_id` survit à un redémarrage.
3. J'écris la commande de bascule **MySQL → SQLite** (copie table par table) et je la
   teste sur une sauvegarde **anonymisée** (jamais sur des données réelles).

### Ce que tu fais (15 min)

1. **Relis et fusionne la pull request** quand la CI est verte. Tu n'as pas besoin de
   comprendre le contenu ; tu vérifies que les tests passent et que je t'ai expliqué le
   changement en français.
2. Quand je te le demande, **pose un tag de test** `v1.x.y-docker.1` : Actions →
   « Tag de version » → *Run workflow* → version. Ça déclenche la construction de
   l'image. Un tag de test ne déploie rien chez personne.
3. Remets la permission **Workflows** à *No access* (étape 0.4 à l'envers).

### ✅ Fin de phase 1

Il existe une image `ghcr.io/guim31/ghosteo:<version>`, privée, qui démarre GHosteo
toute seule. Tu peux le voir sur GitHub → ton profil → **Packages**.

---

## Phase 2 — Serveur de contrôle, Dokploy et staging

**Impact clients : aucun.** On crée une machine neuve, vide, chez Scaleway.

### Ce que je fais

1. Je crée le **serveur de contrôle** chez Scaleway (Paris, 4 Go de RAM) avec un script
   d'installation automatique (Docker, pare-feu, mises à jour de sécurité automatiques).
2. J'installe **Dokploy** dessus et je te donne l'adresse `https://panel.ghosteo.eu`
   (après avoir ajouté cette ligne DNS chez OVH, que je te dicterai si tu préfères la
   saisir toi-même).
3. Une fois ton compte créé (ci-dessous), je déploie **staging** depuis l'image, avec des
   données anonymisées, et je vérifie le cycle « nouveau tag → redéploiement » deux fois.

### Ce que tu fais (30 min)

1. **Crée le compte administrateur Dokploy** : ouvre l'adresse que je te donne, choisis un
   mot de passe long et unique, enregistre-le dans ton gestionnaire de mots de passe.
   Je ne le connaîtrai jamais. Active la double authentification dans *Settings →
   Profile*.
2. **Crée un jeton d'API Dokploy** : *Settings → API/CLI → Generate token*. Colle-le
   moi ; je le range à côté de la clé Scaleway.
3. **Crée un jeton GitHub de lecture des images** : Settings → Developer settings →
   **Personal access tokens (classic)** → *Generate new token* → nom `dokploy-ghcr`,
   expiration 1 an, coche uniquement **`read:packages`**. Ce jeton ne sait que
   télécharger tes images, rien d'autre.
4. **Renseigne ce jeton dans Dokploy** : *Settings → Registry → Add registry* →
   URL `ghcr.io`, utilisateur `guim31`, mot de passe = le jeton. Il ne passe pas par moi.

### ✅ Fin de phase 2

Tu ouvres `https://staging.ghosteoapp.eu` et tu vois GHosteo tourner depuis l'image, sur
Scaleway. Tu peux te connecter avec les identifiants de staging habituels.

---

## Phase 3 — Le back-office sait déployer sur Dokploy

**Impact clients : aucun.** On modifie le code de ghosteo.eu, qui continue de tourner
comme avant sur l'ancien serveur ; la nouveauté est une option de plus dans l'écran de
déploiement.

### Ce que je fais

1. J'ajoute dans `ghosteoeu-main` la table des serveurs, le client Dokploy, les
   nouvelles étapes de déploiement et l'étape DNS. Pull request, CI, explication en
   français.
2. Après fusion, je déploie ghosteo.eu **comme d'habitude, via Vito** (rien ne change
   pour lui à ce stade).
3. Je déploie un **client fictif** `test-migration.ghosteoapp.eu` depuis le wizard, puis
   je le supprime. Je le refais trois fois pour être sûr que c'est reproductible.

### Ce que tu fais (20 min)

1. Fusionne la pull request quand elle est verte.
2. Dans l'admin de ghosteo.eu → **Réglages → Déploiement**, renseigne l'URL de Dokploy et
   le jeton d'API (le même qu'en 2.2). Ils sont chiffrés dans la base du back-office.
3. Ouvre l'écran **Déploiements** et regarde le client fictif se créer tout seul : c'est
   l'écran que tu utiliseras pour chaque nouveau client, désormais.

### ✅ Fin de phase 3

Depuis l'admin de ghosteo.eu, un clic crée une instance cliente complète sur Scaleway,
avec son adresse et son certificat, en moins de cinq minutes.

---

## Phase 4 — DNS chez Scaleway, premier serveur clients, démo

**Impact clients : aucun.** La démo sera coupée dix minutes, ce n'est pas un client.

### 4.1 Déplacer l'annuaire de `ghosteoapp.eu` (toi 10 min, moi le reste)

Rappel : les **noms** restent achetés chez OVH ; on déplace seulement l'**annuaire**
(la zone DNS) chez Scaleway, pour que le back-office puisse y écrire.
`ghosteo.eu` ne bouge pas : il porte tes e-mails, on ne le touche pas.

1. **Toi** : dans l'espace client OVH → Web Cloud → Noms de domaine → `ghosteoapp.eu` →
   onglet **Zone DNS** → bouton **Exporter la zone**. Envoie-moi le fichier (ou colle
   son contenu). C'est la liste actuelle des lignes, pour que je la recopie à
   l'identique.
2. **Moi** : je recrée la zone chez Scaleway, ligne pour ligne, et je vérifie que les
   deux annuaires répondent la même chose pour chaque nom existant.
3. **Toi** : dans le même écran OVH, onglet **Serveurs DNS** → **Modifier les serveurs
   DNS** → remplace par les deux noms que je te donnerai (`ns0.dom.scw.cloud` et
   `ns1.dom.scw.cloud`). Valide.
4. La propagation prend de quelques minutes à quelques heures. Pendant ce temps, **les
   deux annuaires disent la même chose**, donc personne ne voit rien. Je surveille.
5. Retour arrière si besoin : remettre les serveurs DNS OVH d'origine dans le même écran.

### 4.2 Premier serveur clients (moi)

Je crée `worker-01` (8 Go de RAM) avec le même script d'installation, je l'attache à
Dokploy et je le déclare dans le back-office avec un plafond de 12 instances. Je le
teste avec un client fictif.

### 4.3 La démo (moi, 10 min de coupure)

Je migre `demo.ghosteo.eu` en premier : elle a exactement la forme d'une instance
cliente, sans client derrière. C'est la **répétition générale** du protocole de la
phase 5. Tu la testes ensuite depuis ton navigateur.

### ✅ Fin de phase 4

La démo tourne sur Scaleway. Le back-office crée des lignes DNS tout seul. Le protocole
de migration a été joué une fois de bout en bout, sans client.

---

## Phase 5 — Migration des clients, un par un

**Impact : 15 à 30 minutes d'indisponibilité par client, planifiée avec lui.**

### Avant chaque client (toi)

1. **Préviens le client** deux ou trois jours avant : « Votre logiciel sera indisponible
   le [jour] entre [heure] et [heure + 1 h] pour une migration vers un hébergement plus
   robuste. Vos données sont conservées à l'identique. » Un soir ou un week-end.
2. Dis-moi le créneau. Je ne bascule **jamais** un client sans ce créneau.

### Pendant (moi, tu peux regarder)

| Minute | Ce qui se passe | Retour arrière possible ? |
|---|---|---|
| 0 | Sauvegarde complète depuis l'ancien serveur (base + documents patients + clé de chiffrement) | oui, rien n'a changé |
| 2 | Mise en maintenance de l'ancienne instance : le client voit une page « maintenance en cours » | oui, une commande |
| 3 | Seconde sauvegarde, à froid, pour être sûr de ne rien perdre entre les deux | oui |
| 5 | Création de la nouvelle instance sur `worker-01`, **avec la même clé de chiffrement** | oui, l'ancienne est intacte |
| 10 | Restauration de la sauvegarde, vérification : nombre de patients, de consultations, de documents, identiques à l'ancienne | oui |
| 15 | Bascule de l'adresse `client.ghosteoapp.eu` vers le nouveau serveur | oui, rebasculer l'adresse |
| 20 | Vérification : connexion, dossier patient, création d'une facture de test puis suppression, licence reconnue | oui |
| 25 | Message au client : « c'est terminé » | — |

L'ancienne instance **reste en maintenance, données intactes, pendant 30 jours**. Si le
client signale un problème, on rebascule l'adresse en cinq minutes et on comprend à tête
reposée.

### Après (toi, 5 min)

Demande au client de se connecter et de faire une action normale. C'est la seule
validation qui compte.

### Rythme conseillé

Un client par soirée les deux premières fois, puis deux ou trois par créneau une fois
la routine installée. Ton propre cabinet passe **en premier** : c'est le client le plus
tolérant et le plus exigeant à la fois.

---

## Phase 6 — ghosteo.eu, puis l'ancien serveur

### 6.1 Bascule de ghosteo.eu (moi, nuit, aucun impact visible)

Le serveur de licences est le dernier à bouger, parce que toutes les instances lui
parlent. Elles gardent leur licence en cache **12 heures** et fonctionnent sans lui : une
coupure de quelques minutes est invisible. Même protocole : sauvegarde, maintenance,
restauration sur le serveur de contrôle, bascule de l'adresse, vérification que les
instances continuent de se signaler.

### 6.2 Extinction de l'ancien serveur (toi, après 30 jours)

Quand le dernier client migré a passé 30 jours sans incident :

1. Je fais une **sauvegarde finale** complète de l'ancien serveur, chiffrée, sur le
   stockage objet Scaleway (pas sur le NAS de la maison : ce sont des données de santé).
2. Tu résilies le VPS OVH depuis ton espace client.
3. On **révoque et recrée** la clé Scaleway et le jeton Dokploy qui ont transité par la
   conversation (règle des secrets, § 0).

### ✅ Fin

Tout tourne sur Scaleway. Ajouter un client = un écran dans ton back-office. Ajouter un
serveur = me demander « crée worker-02 ». Mettre à jour tous les clients = poser un tag
puis lancer la cascade depuis le back-office, la nuit.

---

## Ce qui peut mal tourner, et ce qu'on fait

| Situation | Ce qu'on fait |
|---|---|
| L'image ne démarre pas (phase 1) | Rien n'est en production. On corrige, on repose un tag de test. |
| Dokploy ne répond plus | Les instances continuent de tourner : Dokploy ne sert qu'à déployer. On le redémarre ou on le réinstalle. |
| Le DNS mal recopié (phase 4) | On remet les serveurs DNS OVH d'origine dans l'espace client, en 2 minutes. |
| Une restauration montre des chiffres différents (phase 5) | On ne bascule pas l'adresse. Le client reste sur l'ancien serveur, on sort de maintenance, on analyse sur la copie. |
| Un client migré signale un problème | On rebascule son adresse vers l'ancienne instance, remise en service. Il n'a rien perdu : l'ancienne base est celle du jour de la migration, et je récupère ce qu'il a saisi depuis sur la nouvelle. |
| Le serveur de licences est injoignable | Les instances fonctionnent 12 h sans lui, puis passent en mode dégradé sans bloquer l'accès aux dossiers. |

---

## Ta liste, tout en un

- [ ] 0.1 Compte Scaleway pro, projet `ghosteo`, double authentification
- [ ] 0.2 Clé d'API Scaleway → me la coller
- [ ] 0.3 Clé SSH du Beelink ajoutée dans Vito
- [ ] 0.4 Permission Workflows sur le jeton GitHub (temporaire)
- [ ] 0.5 Formulation HDS validée par un juriste → me la donner
- [ ] 1 Fusionner la PR `ghosteo`, poser le tag de test, retirer Workflows
- [ ] 2 Compte admin Dokploy + 2FA, jeton API Dokploy → me le coller, jeton ghcr saisi dans Dokploy
- [ ] 3 Fusionner la PR `ghosteoeu-main`, saisir URL + jeton Dokploy dans Réglages → Déploiement
- [ ] 4 Exporter la zone `ghosteoapp.eu` chez OVH, puis changer les serveurs DNS
- [ ] 5 Un créneau par client, message avant, vérification après
- [ ] 6 Résilier le VPS OVH après 30 jours, révoquer les clés
