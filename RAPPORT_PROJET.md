# Rapport de projet — Pipeline de traitement de transactions

## 1. Présentation

Ce projet met en œuvre une pipeline de données qui traite des transactions financières provenant de fichiers CSV et d'images de reçus. Les résultats sont agrégés puis enregistrés dans PostgreSQL. MinIO fournit le stockage objet compatible S3 utilisé pour les fichiers d'entrée.

Le projet couvre trois étapes fonctionnelles :

1. Générer et agréger des transactions CSV.
2. Stocker et lire les fichiers depuis MinIO.
3. Extraire les informations des reçus PNG avec Tesseract et les traiter comme des transactions.

Les données d'exemple générées par le projet sont déterministes et fictives.

## 2. Architecture

```text
generate_csv.py ──> MinIO (CSV) ──> pipeline.py ──> processing.py ──> PostgreSQL
generate_images.py ──> images PNG ──> MinIO ──> OCR ──┘
```

La pipeline vérifie l'accès au bucket, énumère les objets CSV et PNG, initialise le schéma PostgreSQL, puis traite les fichiers non encore enregistrés. Les fonctions d'agrégation de `processing.py` restent indépendantes des accès à la base de données.

## 3. Traitements effectués

Pour chaque transaction, les champs traités sont la date, les IBAN d'origine et de destination, les pays, la banque source et le montant.

La pipeline :

- calcule les montants cumulés par IBAN d'origine ;
- calcule les montants cumulés par banque source ;
- calcule les montants cumulés par IBAN destinataire ;
- enregistre les transactions dont le montant est strictement supérieur à 5 000 ;
- pour les images, extrait puis normalise les champs requis, valide les dates, les IBAN et les montants, et signale les erreurs OCR par une exception dédiée.

Les montants sont manipulés avec `Decimal` pour éviter les imprécisions habituelles des nombres flottants.

## 4. Stockage et fiabilité

### MinIO / S3

Le bucket utilisé est `transactions`. Les fichiers CSV générés par `generate_csv.py` sont téléversés par défaut. `generate_images.py` crée des reçus PNG sur le disque ; la pipeline peut traiter les PNG présents dans le bucket.

Les téléchargements S3 sont réessayés jusqu'à trois fois après l'essai initial. Les délais entre les essais sont de 1, 2 et 4 secondes.

### PostgreSQL et déduplication

Le schéma (`schema.sql`) définit les tables suivantes :

| Table | Rôle |
|---|---|
| `fichiers_traites` | Suivi des fichiers et empreintes SHA-256 pour éviter les doublons |
| `sommes_par_iban_origine` | Totaux par IBAN d'origine et fichier |
| `sommes_par_banque` | Totaux par banque source et fichier |
| `sommes_recues_par_iban` | Totaux reçus par IBAN destinataire et fichier |
| `transactions_flaggees` | Détail des transactions dépassant le seuil |

L'empreinte du contenu empêche également de traiter deux fois des fichiers ayant des noms différents mais un contenu identique. L'enregistrement de la marque de traitement et des résultats s'effectue dans une même transaction SQL.

Les insertions sont réessayées jusqu'à trois fois après l'essai initial, avec des délais de 1, 2 et 4 secondes. Si tous les essais échouent, l'erreur est propagée.

## 5. Technologies

- Python et pytest
- PostgreSQL (image `postgres:17-alpine` dans Docker Compose)
- MinIO et boto3
- Pillow et pytesseract ; le moteur Tesseract doit également être installé pour effectuer un véritable OCR
- Docker Compose pour démarrer PostgreSQL et MinIO

## 6. Démarrage local

Depuis la racine du dépôt, sous PowerShell :

```powershell
$env:PGPASSWORD = "postgres-local-password"
docker compose up -d
python -m pip install -r requirements.txt -r requirements-dev.txt
python generate_csv.py
python pipeline.py
```

La variable `PGPASSWORD` est définie explicitement pour conserver le même mot de passe entre le conteneur PostgreSQL et la connexion de l'application. Les paramètres PostgreSQL peuvent aussi être configurés via `DATABASE_URL` ou les variables `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGHOST` et `PGPORT`.

Pour générer des images de reçus dans un dossier local :

```powershell
python generate_images.py --output-dir generated_receipts
```

Le moteur Tesseract doit être installé séparément. Si son exécutable n'est pas dans le `PATH`, définir `TESSERACT_CMD` avec son chemin avant d'exécuter la pipeline.

## 7. Tests

Exécuter les tests avec :

```powershell
python -m pytest -q
```

Les tests couvrent les agrégations, le seuil de signalement, la génération et le téléchargement S3, le parsing CSV, l'extraction et la validation OCR, ainsi que l'orchestration et les mécanismes de retry. Le test d'intégration PostgreSQL utilise une base dédiée indiquée par `TEST_DATABASE_URL` ; sans cette variable, ce test est ignoré.

## 8. Résultat de validation

À la rédaction de ce rapport, après installation des dépendances déclarées, la commande `python -m pytest -q` a produit le résultat suivant :

```text
21 passed, 1 skipped
```

Le test ignoré nécessite une base PostgreSQL de test configurée via `TEST_DATABASE_URL`.
