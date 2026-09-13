<!-- Issue ouverte le 13/09/2026 : https://github.com/guim31/ghosteo/issues/204
     Ce fichier garde le texte source, au cas où le ticket
     serait à rouvrir ou à reformuler. Voir aussi SUIVI.md, section « Incident : avatars
     et signatures manuscrites perdus à la migration ». -->

# Titre

fix(image) : avatars et signatures vivent dans `public/`, donc hors du volume — perdus à chaque redéploiement (échéance : 13/10/2026)

# Corps

## ⏳ Date butoir : 13 octobre 2026

C'est la date de résiliation du VPS OVH. Il détient aujourd'hui la **seule autre copie** de
ces fichiers. Après cette date, un redéploiement d'instance les effacerait sans recours.

## Le constat

Les avatars et les signatures manuscrites sont écrits dans **`public/avatars/` et
`public/signature/`**, à la racine de l'application :

```
users.avatar    -> public/avatars/4_avatar_1760274245.png
users.signature -> public/signature/3_signature_1767009112.png
```

Or, dans l'image Docker, `public/` fait partie de **l'image** et non du volume. Le seul
volume d'une instance est `/var/www/html/storage`. Conséquence directe : **tout
redéploiement recrée le conteneur depuis l'image et efface ces fichiers.** La base, elle,
continue de les référencer, et l'application affiche des images cassées.

La signature n'est pas un agrément : l'écran des réglages indique que **sans elle, aucune
note d'honoraires ne peut être éditée**.

## Comment le défaut s'est manifesté

Migration du SaaS vers Scaleway, septembre 2026. La procédure de migration copiait
`storage/app` et rien d'autre — ce qui était cohérent avec « tout l'état d'une instance est
dans le volume ». **13 fichiers ont ainsi été laissés derrière, chez 5 cabinets sur 7.**
Un praticien a signalé que son avatar avait disparu et que les signatures de son cabinet
n'étaient plus là.

Les fichiers ont été remis à la main dans les conteneurs en service, et une copie de
sauvegarde déposée dans `storage/app/public-assets/`. **Cette réparation ne survivra pas au
prochain redéploiement** : c'est bien le correctif ci-dessous qui clôt le sujet.

## Correctif proposé

Dans `docker/entrypoint.d/`, déplacer les deux répertoires dans le volume au premier
démarrage, puis les remplacer par des liens symboliques. Idempotent, silencieux quand c'est
déjà fait :

```sh
for d in avatars signature; do
    cible="storage/app/public-assets/$d"
    mkdir -p "$cible"
    if [ -d "public/$d" ] && [ ! -L "public/$d" ]; then
        # -n : ne remplace JAMAIS un fichier déjà présent dans le volume, qui fait foi.
        cp -an "public/$d/." "$cible/" 2>/dev/null || true
        rm -rf "public/$d"
    fi
    ln -sfn "/var/www/html/$cible" "public/$d"
done
```

Le premier démarrage après correctif récupère donc au passage les fichiers restés dans
l'image, y compris `default.jpg` et `exemple_signature.webp`.

## Pourquoi cette voie plutôt que deux volumes de plus

Ajouter `public/avatars` et `public/signature` comme volumes dans le gabarit compose
marcherait aussi, mais :

1. Le back-office crée les instances depuis **son propre** gabarit
   (`DokployComposeTemplate` dans `ghosteoeu-main`). Il faudrait le modifier en parallèle,
   et les deux gabarits divergeraient tôt ou tard.
2. Ces fichiers n'entreraient toujours **dans aucune sauvegarde** : celles-ci prennent
   `storage/app` et la base. Dans le volume `storage`, ils sont sauvegardés sans rien
   changer d'autre.
3. Un seul volume par instance reste plus simple à raisonner et à restaurer.

## Critères d'acceptation

- [ ] Après redéploiement d'une instance, avatars et signatures sont **toujours là**.
- [ ] `public/avatars` et `public/signature` sont des liens vers le volume.
- [ ] Une instance neuve (créée par le wizard du back-office) obtient le même comportement,
      sans intervention.
- [ ] Les fichiers apparaissent dans l'archive `storage.tar.gz` d'une sauvegarde.
- [ ] `default.jpg` et `exemple_signature.webp` restent servis.
- [ ] Un dépôt d'avatar et de signature depuis l'application fonctionne toujours.

## Après la fusion

Poser un tag de version, puis passer le parc sur la nouvelle image par la cascade du
back-office. **Jusque-là, éviter toute mise à jour d'instance** : elle effacerait la
réparation manuelle.
