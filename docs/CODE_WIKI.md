# Code Wiki — Hospital Risk Prediction

## Objectif du dépôt

Ce dépôt implémente une mini-plateforme d’analytics hospitalier orientée “portfolio/POC” avec :
- un pipeline ETL en scripts Python (Extract → Transform → Load)
- un stockage PostgreSQL (via Docker Compose)
- un modèle scikit-learn exporté (RandomForest) pour prédire un niveau de risque
- un dashboard Streamlit qui lit PostgreSQL et permet une prédiction interactive

## Architecture globale

### Vue d’ensemble (flux)

1. **Extract** : télécharge des sources open-data (MIMIC-IV Demo + KPI) et produit des CSV “raw”.
2. **Transform** : nettoie, contraint les ranges, impute, calcule `risk_score` et `risk_level`, et produit un CSV “processed”.
3. **Load** : crée/alimente les tables PostgreSQL depuis les CSV/ODS.
4. **Train** : entraîne un pipeline sklearn et sérialise `ml/models/risk_model.joblib`.
5. **Dashboard** : lit les tables PostgreSQL, affiche des KPI et permet des prédictions via le modèle.

### Composants et dépendances

- **ETL (Python)** : [etl](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl)
- **ML (Python / scikit-learn)** : [ml](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/ml)
- **Dashboard (Streamlit)** : [dashboard](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard)
- **DB (PostgreSQL)** : service `db` dans [docker-compose.yml](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/docker-compose.yml#L1-L45)

## Structure du dépôt

```text
hospital-risk-prediction/
├─ dashboard/
│  └─ streamlit_app.py
├─ data/
│  ├─ raw/
│  │  ├─ patient_vitals_mimic_demo_raw.csv
│  │  ├─ mimic_iv_demo/...
│  │  ├─ nhs_scotland/monthly_ae_activity_waiting_times.csv
│  │  └─ cqc/adult_inpatient_survey_2024/*.ods
│  └─ processed/patient_vitals_processed.csv
├─ etl/
│  ├─ extract/build_raw_from_mimic_iv_demo.py
│  ├─ transform/transform_patient_vitals.py
│  └─ load/load_patient_vitals_to_postgres.py
├─ ml/
│  ├─ training/train_risk_model.py
│  └─ models/risk_model.joblib
├─ Dockerfile
├─ docker-compose.yml
└─ requirements.txt
```

## Modules majeurs

### 1) Extract — `etl/extract/build_raw_from_mimic_iv_demo.py`

Référence : [build_raw_from_mimic_iv_demo.py](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/extract/build_raw_from_mimic_iv_demo.py)

**Responsabilités**
- Télécharger et dézipper **MIMIC-IV Demo** depuis PhysioNet en ZIP.
- Construire un CSV “raw” patient-level: `data/raw/patient_vitals_mimic_demo_raw.csv`.
- Optionnel : télécharger des datasets KPI (A&E NHS Scotland, CQC Adult Inpatient Survey 2024).

**Fonctions clés**
- `parse_args()` : définit la CLI (version, chemins, options de téléchargement, mode `--force`).  
  [parse_args](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/extract/build_raw_from_mimic_iv_demo.py#L62-L99)
- `sha256_file(path)` : calcule le SHA256 d’un ZIP (validation optionnelle).  
  [sha256_file](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/extract/build_raw_from_mimic_iv_demo.py#L102-L107)
- `download(url, dest)` : téléchargement HTTP en fichier `.part`, puis rename atomique.  
  [download](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/extract/build_raw_from_mimic_iv_demo.py#L110-L116)
- `extract_zip(zip_path, out_dir)` : extraction ZIP.  
  [extract_zip](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/extract/build_raw_from_mimic_iv_demo.py#L118-L122)
- `find_mimic_root(extract_dir)` : détecte le dossier racine contenant `hosp/` et `icu/`.  
  [find_mimic_root](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/extract/build_raw_from_mimic_iv_demo.py#L124-L132)
- `_first_by_stay(events, itemid, col_name)` : extrait la première mesure par `stay_id` pour un `itemid` MIMIC.  
  [_first_by_stay](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/extract/build_raw_from_mimic_iv_demo.py#L134-L144)
- `main()` : orchestre l’ensemble : téléchargement → extraction → lecture CSV gzip → jointures → export CSV raw.  
  [main](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/extract/build_raw_from_mimic_iv_demo.py#L147-L340)

**Sorties produites**
- CSV raw patient/vitals : `data/raw/patient_vitals_mimic_demo_raw.csv` (colonnes : `patient_id`, `recorded_at`, `age`, `temperature_c`, `systolic_bp`, `diastolic_bp`, `spo2`, `heart_rate`, `glucose_mg_dl`, `pain_score`, `stress_level`, `satisfaction_score`, `admission_type`).

### 2) Transform — `etl/transform/transform_patient_vitals.py`

Référence : [transform_patient_vitals.py](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/transform/transform_patient_vitals.py)

**Responsabilités**
- Normaliser les types, contraindre des ranges physiologiques, dédupliquer.
- Imputer les valeurs manquantes (médiane).
- Calculer `risk_score` (règles) puis `risk_level`.
- Exporter : `data/processed/patient_vitals_processed.csv`.

**Types / fonctions clés**
- `TransformConfig` : dataclass de configuration (input/output).  
  [TransformConfig](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/transform/transform_patient_vitals.py#L9-L13)
- `parse_args()` : CLI `--input`, `--output`.  
  [parse_args](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/transform/transform_patient_vitals.py#L15-L21)
- `coerce_numeric(df, cols)` : convertit en numérique avec `errors="coerce"`.  
  [coerce_numeric](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/transform/transform_patient_vitals.py#L23-L27)
- `clip_ranges(df)` : applique des bornes de sécurité (âge, TA, SpO2, etc.).  
  [clip_ranges](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/transform/transform_patient_vitals.py#L30-L40)
- `impute_medians(df, cols)` : remplit les NaN par médiane colonne.  
  [impute_medians](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/transform/transform_patient_vitals.py#L43-L49)
- `compute_risk_score(row)` : scoring (âge, température, BP, SpO2, HR, glucose, douleur).  
  [compute_risk_score](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/transform/transform_patient_vitals.py#L51-L107)
- `compute_risk_level(score)` : mapping score → `Low/Medium/High/Critical`.  
  [compute_risk_level](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/transform/transform_patient_vitals.py#L110-L117)
- `main()` : pipeline end-to-end sur le CSV.  
  [main](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/transform/transform_patient_vitals.py#L120-L170)

**Contrat de données (processed)**
- Colonnes attendues pour l’entraînement et le chargement PostgreSQL :  
  `patient_id`, `recorded_at`, `age`, `temperature_c`, `systolic_bp`, `diastolic_bp`, `spo2`, `heart_rate`, `glucose_mg_dl`, `pain_score`, `admission_type`, `risk_score`, `risk_level`.

### 3) Load — `etl/load/load_patient_vitals_to_postgres.py`

Référence : [load_patient_vitals_to_postgres.py](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py)

**Responsabilités**
- Se connecter à PostgreSQL via variables d’environnement ou arguments CLI.
- Créer les tables (si besoin) et charger les données (COPY).
- Supporte 3 datasets :
  - `patient_vitals` (CSV processed)
  - `nhs_scotland_ae` (CSV A&E)
  - `cqc_aip_2024` (ODS, conversion vers tables TEXT)

**Types / fonctions clés**
- `PgConfig` : dataclass de connexion.  
  [PgConfig](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L14-L21)
- `parse_args()` : CLI `--dataset`, `--csv`, `--schema`, `--table`, `--mode` + params PG.  
  [parse_args](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L23-L48)
- `connect(cfg)` : construit la connexion (priorité à `DATABASE_URL`, sinon params).  
  [connect](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L64-L86)
- `create_table_patient_vitals(...)` : table typée + PK `(patient_id, recorded_at)` + index.  
  [create_table_patient_vitals](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L92-L128)
- `copy_csv_patient_vitals(...)` : COPY depuis CSV processed.  
  [copy_csv_patient_vitals](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L138-L149)
- `create_table_nhs_scotland_ae(...)` : table KPI urgences + index.  
  [create_table_nhs_scotland_ae](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L151-L201)
- `copy_csv_nhs_scotland_ae(...)` : normalise les colonnes et gère les valeurs “Z”.  
  [copy_csv_nhs_scotland_ae](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L230-L310)
- `load_cqc_aip_2024(...)` : lit des ODS, choisit la “meilleure” feuille et crée une table TEXT par fichier.  
  [load_cqc_aip_2024](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L361-L451)
- `main()` : sélection dataset, choix CSV, DDL/DML selon `--mode`.  
  [main](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L454-L509)

**Modes de chargement**
- `replace` (défaut) : drop table puis recreate + load.
- `truncate` : table conservée, TRUNCATE puis load.
- `append` : table conservée, ajout de lignes.

### 4) Train — `ml/training/train_risk_model.py`

Référence : [train_risk_model.py](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/ml/training/train_risk_model.py)

**Responsabilités**
- Charger `data/processed/patient_vitals_processed.csv`.
- Entraîner un pipeline scikit-learn pour prédire `risk_level`.
- Exporter un artefact joblib consommé par le dashboard.

**Types / fonctions clés**
- `TrainConfig` : dataclass de configuration d’entraînement.  
  [TrainConfig](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/ml/training/train_risk_model.py#L15-L21)
- `parse_args()` : CLI `--input`, `--model-out`, `--test-size`, `--random-state`.  
  [parse_args](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/ml/training/train_risk_model.py#L23-L39)
- `main()` : split stratifié, fit, métriques, dump joblib.  
  [main](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/ml/training/train_risk_model.py#L42-L130)

**Pipeline sklearn exporté**
- `preprocess` : `ColumnTransformer` (one-hot sur `admission_type`, reste en passthrough).  
  [preprocessor](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/ml/training/train_risk_model.py#L81-L88)
- `model` : `RandomForestClassifier(n_estimators=400, class_weight="balanced")`.  
  [model](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/ml/training/train_risk_model.py#L89-L101)
- Artefact : `ml/models/risk_model.joblib` contient `{"pipeline": pipeline, "feature_cols": [...]}`.  
  [joblib.dump](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/ml/training/train_risk_model.py#L120-L129)

### 5) Dashboard — `dashboard/streamlit_app.py`

Référence : [streamlit_app.py](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard/streamlit_app.py)

**Responsabilités**
- Accès PostgreSQL (avec cache Streamlit).
- 3 pages :
  - “Patient Risk” : visualisations patient_vitals + prédiction modèle
  - “A&E Waiting Times” : KPI urgences (NHS Scotland)
  - “CQC Survey” : exploration tables CQC (ODS converties)

**Types / fonctions clés**
- `PgConfig` + `_pg_config_from_env()` : lecture `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`.  
  [PgConfig](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard/streamlit_app.py#L13-L32)
- `_connect(cfg)` : DSN via `DATABASE_URL` sinon paramètres.  
  [_connect](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard/streamlit_app.py#L35-L49)
- `load_table(query)` : exécute une requête SQL en cache (`ttl=300`).  
  [load_table](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard/streamlit_app.py#L51-L56)
- `_load_model()` : charge `ml/models/risk_model.joblib` si présent.  
  [_load_model](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard/streamlit_app.py#L58-L63)
- `_patient_vitals_section()` : lecture `public.patient_vitals`, graphiques, form de prédiction + proba + feature importance.  
  [_patient_vitals_section](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard/streamlit_app.py#L65-L205)
- `_ae_waiting_times_section()` : filtres + agrégations temporelles.  
  [_ae_waiting_times_section](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard/streamlit_app.py#L207-L295)
- `_cqc_section()` : preview table + auto-détection colonnes numériques.  
  [_cqc_section](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard/streamlit_app.py#L296-L321)
- `main()` : routing des pages via sidebar.  
  [main](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard/streamlit_app.py#L323-L339)

## Schéma de données (PostgreSQL)

### Table `public.patient_vitals`

Créée par : `create_table_patient_vitals`  
[create_table_patient_vitals](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L92-L128)

- Clé primaire : `(patient_id, recorded_at)`
- Colonnes : `age`, `temperature_c`, `systolic_bp`, `diastolic_bp`, `spo2`, `heart_rate`, `glucose_mg_dl`, `pain_score`, `admission_type`, `risk_score`, `risk_level`

### Table `public.ae_waiting_times`

Créée par : `create_table_nhs_scotland_ae`  
[create_table_nhs_scotland_ae](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L151-L201)

- `month_date` est une date dérivée de `Month` au format `YYYYMM` (premier jour du mois).
- Colonnes de volumes/percentages issues du CSV NHS Scotland, avec gestion des valeurs “Z”.

### Tables CQC AIP 2024

Créées dynamiquement (colonnes TEXT) à partir des headers de l’ODS :
- `public.cqc_aip2024_national`
- `public.cqc_aip2024_trust`
- `public.cqc_aip2024_site`

Implémentation : [load_cqc_aip_2024](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L361-L451)

## Dépendances

### Python

Voir : [requirements.txt](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/requirements.txt)

- `pandas`, `numpy` : ETL + features
- `scikit-learn`, `joblib` : entraînement + sérialisation modèle
- `psycopg2-binary` : PostgreSQL
- `streamlit`, `plotly` : dashboard
- `odfpy` : parsing ODS (CQC)

### Docker

- Image runtime : [Dockerfile](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/Dockerfile)
- Services : [docker-compose.yml](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/docker-compose.yml#L1-L45)
- Fichiers exclus de l’image : [.dockerignore](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/.dockerignore)

## Comment exécuter le projet

### Prérequis

- Python (compatible avec les libs listées) + pip
- Optionnel : Docker + Docker Compose (recommandé pour PostgreSQL)

### Workflow recommandé (local + PostgreSQL Docker)

1) Installer les dépendances Python

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) Démarrer PostgreSQL via Docker Compose

```bash
docker compose up -d db
```

3) Extract (MIMIC-IV Demo + KPI optionnels)

```bash
python etl/extract/build_raw_from_mimic_iv_demo.py --download-nhs-scotland-ae --download-cqc-aip-2024
```

4) Transform (raw → processed)

```bash
python etl/transform/transform_patient_vitals.py
```

5) Load (processed → PostgreSQL)

```bash
python etl/load/load_patient_vitals_to_postgres.py --dataset patient_vitals
python etl/load/load_patient_vitals_to_postgres.py --dataset nhs_scotland_ae
python etl/load/load_patient_vitals_to_postgres.py --dataset cqc_aip_2024
```

6) Entraîner le modèle (optionnel si `ml/models/risk_model.joblib` existe déjà)

```bash
python ml/training/train_risk_model.py
```

7) Lancer le dashboard Streamlit

```bash
streamlit run dashboard/streamlit_app.py
```

### Workflow Docker Compose (DB + dashboard)

Le service `streamlit` lance directement l’app :
- commande définie dans [docker-compose.yml](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/docker-compose.yml#L27-L42)

```bash
docker compose up --build streamlit
```

Notes d’usage :
- Le dashboard suppose que les tables PostgreSQL existent. Exécuter l’ETL + load avant (localement, ou via `docker compose run --rm app python ...`).
- Les variables de connexion DB dans Compose (host `db`, port 5432) sont injectées au conteneur Streamlit.

## Configuration

### PostgreSQL

Variables reconnues par l’ETL et le dashboard :
- `DATABASE_URL` (prioritaire)
- `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`

Implémentations :
- Dashboard : [_pg_config_from_env](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard/streamlit_app.py#L22-L32), [_connect](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/dashboard/streamlit_app.py#L35-L49)
- Loader : [parse_args](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L23-L48), [connect](file:///c:/Users/djami/Desktop/devIA/project/hospital-risk-prediction/etl/load/load_patient_vitals_to_postgres.py#L64-L86)

## Relations entre modules (dépendances fonctionnelles)

- Extract → Transform : `data/raw/patient_vitals_mimic_demo_raw.csv`
- Transform → Train : `data/processed/patient_vitals_processed.csv`
- Transform → Load : `data/processed/patient_vitals_processed.csv` → `public.patient_vitals`
- Extract (KPI) → Load : CSV/ODS → `public.ae_waiting_times` + `public.cqc_aip2024_*`
- Train → Dashboard : `ml/models/risk_model.joblib`
- Load → Dashboard : lectures SQL sur `public.patient_vitals`, `public.ae_waiting_times`, `public.cqc_aip2024_*`

## Notes et points d’attention

- Le label `risk_level` est dérivé de règles dans `transform_patient_vitals.py` puis appris par le modèle, ce qui fait du ML une “approximation” des règles plutôt qu’une prédiction d’outcome clinique.
- Le service `app` du Compose build l’image et monte le repo, mais ne lance pas de commande par défaut (utile pour lancer ETL/ML manuellement dans un conteneur).

