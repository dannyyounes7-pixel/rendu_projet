# Mini-projet Data Engineering — Intégration continue

**Réalisé par : Yacine BAKOUR et Nawfel Chakib YOUNES**

## Présentation

Pipeline data complète partant de fichiers CSV de transactions financières jusqu'à l'insertion en base de données relationnelle, avec stockage objet S3 local et extraction OCR depuis des images.

Le projet est découpé en 3 niveaux de complexité croissante.

---

## Structure des fichiers

```
mini_projet_DE/
├── data/
│   └── csv/                        # CSV générés (non versionnés)
├── db/
│   └── schema.sql                  # Schéma PostgreSQL
├── src/
│   ├── generate_csv.py             # Génération de données déterministes
│   ├── generate_images.py          # Génération d'images de reçus (Niveau 3)
│   ├── processing.py               # Fonctions pures de traitement
│   ├── ocr_processing.py           # Extraction OCR depuis images (Niveau 3)
│   ├── s3_client.py                # Client MinIO/S3 (Niveau 2)
│   ├── database.py                 # Connexion PostgreSQL, insertion, retry
│   └── pipeline.py                 # Orchestration complète
├── tests/
│   ├── test_processing.py          # Tests unitaires (sans DB)
│   └── test_integration.py         # Tests d'intégration (avec DB)
├── docker-compose.yml              # PostgreSQL + MinIO
├── requirements.txt
└── README.md
```

---

## Stack technique

| Composant | Outil |
|---|---|
| Langage | Python 3.12 |
| Base de données | PostgreSQL 16 |
| Driver DB | psycopg2 |
| Stockage objet | MinIO (S3 local) |
| Client S3 | boto3 |
| OCR | Tesseract + pytesseract |
| Génération images | Pillow |
| Tests | pytest |
| Conteneurs | Docker / Docker Compose |

---

## Niveau 1 — Pipeline locale

### Fonctionnement

```
generate_csv.py → processing.py → database.py → PostgreSQL
```

### Données générées

Chaque CSV contient des transactions financières avec les champs :

- `datetime_transaction`
- `iban_origine`
- `pays_source`
- `banque_source`
- `iban_destinataire`
- `pays_destinataire`
- `montant`

### Traitements effectués

- Somme des montants envoyés par IBAN origine
- Somme des montants envoyés par banque source
- Somme des montants reçus par IBAN destinataire
- Flag des transactions dont le montant dépasse 5 000 €

### Schéma de la base de données

| Table | Clé unique | Description |
|---|---|---|
| `somme_par_iban_origine` | `iban_origine` | Montant total envoyé par IBAN |
| `somme_par_banque` | `banque_source` | Montant total envoyé par banque |
| `somme_recue_par_iban` | `iban_destinataire` | Montant total reçu par IBAN |
| `transactions_flaggees` | — | Transactions > 5 000 € |
| `fichiers_traites` | `nom_fichier` | Suivi anti-doublon |

### Mécanisme de retry

En cas d'échec d'insertion, la pipeline réessaie jusqu'à **3 fois** avec un délai croissant entre chaque tentative (backoff linéaire).

### Mécanisme anti-doublon

La table `fichiers_traites` enregistre chaque CSV après insertion réussie. À chaque run, la pipeline consulte cette table avant de traiter un fichier. Un fichier déjà traité est ignoré, même en cas de retry.

---

## Niveau 2 — Stockage S3 local (MinIO)

Les fichiers CSV ne sont plus stockés sur le filesystem local mais dans un bucket S3 géré par MinIO.

### Flux

```
generate_csv.py → upload S3 → lecture S3 → processing.py → PostgreSQL
```

### Bucket

Nom du bucket : `transactions`

### Retry sur lecture S3

En cas d'échec de téléchargement depuis S3 (timeout, indisponibilité), le client réessaie jusqu'à 3 fois avec backoff avant de lever une exception.

---

## Niveau 3 — OCR sur images

La pipeline prend également en charge des images de reçus de transactions. L'OCR extrait les données de transaction depuis chaque image et les intègre au traitement existant.

### Flux

```
generate_images.py → upload S3 → téléchargement → OCR → processing.py → PostgreSQL
```

### Outil utilisé

Tesseract via `pytesseract`. Les images sont générées avec `Pillow` au format PNG.

---

## Lancement rapide

### Prérequis

- Docker et Docker Compose installés
- Python 3.12
- Tesseract installé sur le système

```bash
# Ubuntu / Debian
sudo apt install tesseract-ocr

# macOS
brew install tesseract
```

### Démarrage

```bash
# 1. Lancer PostgreSQL et MinIO
docker compose up -d

# 2. Installer les dépendances Python
pip install -r requirements.txt

# 3. Lancer la pipeline complète
cd src && python pipeline.py

# 4. Tests unitaires (sans DB)
pytest tests/test_processing.py -v

# 5. Tests d'intégration (DB requise)
pytest tests/test_integration.py -v
```

---

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `DB_HOST` | `localhost` | Hôte PostgreSQL |
| `DB_PORT` | `5432` | Port PostgreSQL |
| `DB_NAME` | `transactions_db` | Nom de la base |
| `DB_USER` | `postgres` | Utilisateur PostgreSQL |
| `DB_PASSWORD` | `postgres` | Mot de passe PostgreSQL |
| `DB_RETRY_MAX` | `3` | Nombre max de tentatives d'insertion |
| `DB_RETRY_DELAI` | `2.0` | Délai initial entre tentatives (secondes) |
| `MINIO_ENDPOINT` | `localhost:9000` | Endpoint MinIO |
| `MINIO_ACCESS_KEY` | `minioadmin` | Clé d'accès MinIO |
| `MINIO_SECRET_KEY` | `minioadmin` | Clé secrète MinIO |
| `MINIO_BUCKET` | `transactions` | Nom du bucket |
| `S3_RETRY_MAX` | `3` | Nombre max de tentatives lecture S3 |

---

## Mécanismes clés

### Fonctions pures

Toutes les fonctions de traitement dans `processing.py` sont **pures** : elles ne lisent ni n'écrivent rien sur le disque ou en base. Elles prennent une liste de transactions en entrée et retournent un résultat. Cela les rend **testables unitairement** sans aucune dépendance externe.

### Anti-doublon

La table `fichiers_traites` est le mécanisme central de déduplication. Chaque fichier (CSV ou image) est enregistré après insertion réussie. En cas de retry ou de relance de la pipeline, les fichiers déjà traités sont détectés et ignorés immédiatement.

### Retry avec backoff

Les deux points de défaillance potentiels (insertion DB et lecture S3) sont couverts par un mécanisme de retry identique : jusqu'à 3 tentatives, avec un délai qui augmente à chaque échec (`delai × tentative`). Si toutes les tentatives échouent, une exception est levée et propagée à la pipeline.
