<!-- Texte prêt à coller dans une issue du dépôt ghosteo.
     Rédigé le 12/09/2026 ; l'agent n'a pas le droit « Issues » sur le jeton GitHub. -->

# Titre

perf(image) : réduire le cache de code PHP, deux tiers de la mémoire d'une instance servent à deux processus qui dorment

# Corps

## Constat, mesuré sur worker-01 le 12/09/2026

Une instance GHosteo en conteneur occupe **148 Mo de mémoire non récupérable**, répartis ainsi :

| Conteneur | mémoire propre (`anon`) | mémoire partagée (`shmem`) | noyau | total |
|---|---|---|---|---|
| `web` | 11 Mo | 24 à 31 Mo | 9 à 11 Mo | 45 à 53 Mo |
| `scheduler` | 17 Mo | 27 Mo | 4 Mo | 48 Mo |
| `queue` | 18 Mo | 27 Mo | 4 Mo | 50 Mo |

**Les deux conteneurs secondaires pèsent 98 Mo sur 148, soit les deux tiers**, alors qu'ils
consomment 0,1 % de processeur : `schedule:work` dort entre deux minutes, `queue:work`
interroge une file vide.

La mémoire partagée de 27 Mo par conteneur est le cache de code de PHP. Or :

```
opcache.enable_cli = 1
opcache.memory_consumption = 128   # Mo réservés
utilisé réellement = 8 Mo
```

## Piste

Réduire `opcache.memory_consumption` (64 Mo laisserait déjà huit fois la marge nécessaire), et
examiner `opcache.enable_cli` pour `scheduler` et `queue`. Attention : ces deux processus sont
de longue durée, le cache de code leur sert donc réellement — le désactiver franchement n'est
probablement pas souhaitable, le réduire l'est.

Gain attendu : environ 50 Mo par instance, soit **600 Mo à douze cabinets sur un serveur**.

## Pourquoi ce n'est pas urgent

La projection tient sans ce correctif : 12 instances demandent 2 029 Mo sur les 3 909 Mo d'un
DEV1-M, soit 52 %, avec 1,9 Go de marge. Ce ticket devient intéressant au-delà de douze
cabinets par serveur, ou pour éviter de payer un second serveur.

## Comment vérifier une modification

Les indicateurs habituels induisent en erreur : `free` et `docker stats` additionnent le cache
de fichiers, qui est récupérable **et partagé entre instances** puisqu'elles tournent sur la même
image. La bonne mesure est le cgroup du conteneur :

```bash
id=$(docker inspect -f '{{.Id}}' <conteneur>)
awk '/^(anon|shmem|kernel|slab) /{printf "%-8s %6d Mo\n", $1, $2/1048576}' \
  /sys/fs/cgroup/system.slice/docker-$id.scope/memory.stat
```

Recoupement au niveau système : `AnonPages + Shmem + SUnreclaim` de `/proc/meminfo`.

## Contexte

Relevé pendant la migration des instances vers Docker et Scaleway. Détail et mesures dans
`ghosteo-deploy/SUIVI.md`, section « Mesure sérieuse du coût mémoire d'une instance ».
