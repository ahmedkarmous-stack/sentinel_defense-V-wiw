# SENTINEL Defense — Taint Graph + Intent Divergence

Défense pour le challenge SENTINEL (IndabaX Tunisia 2026). Architecture à deux étages :
graphe de provenance persistant par run_id (taint tracking multi-tour) + vérification de
divergence d'intention, fusionnés en un risk score calibré par sigmoid, puis mappés sur
Allow/Block/Escalate/Rewrite via une matrice de seuils indexée par sensibilité d'action.

## Setup (VS Code)

1. Ouvre ce dossier dans VS Code (`File > Open Folder`)
2. Installe l'extension Python si pas déjà fait
3. Crée un environnement virtuel :
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Sélectionne l'interpréteur `.venv` dans VS Code (`Ctrl+Shift+P` → `Python: Select Interpreter`)

## Lancer le serveur de défense

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080
```

Vérifie : `curl http://127.0.0.1:8080/healthz` doit renvoyer `{"status":"ok"}`.

## Tester contre le simulateur officiel

Il te faut le starter kit officiel à côté (clone-le si pas déjà fait) :

```bash
git clone https://github.com/Skan22/Sentinel_Starter_Kit.git
cd Sentinel_Starter_Kit
pip install -e .
```

Un seul scénario :
```bash
python -m sentinel.cli run \
  --scenario scenarios/public/enterprise/enterprise_memory_poison.yaml \
  --defense-url http://127.0.0.1:8080 \
  --model mock \
  --artifacts ./artifacts
```

**Important** : `--defense-url` doit être l'URL de base SANS `/v1/decision` à la fin — le
client l'ajoute lui-même.

Tous les scénarios publiés d'un coup (donne un scorecard complet) :
```bash
python -m sentinel.cli eval public \
  --defense-url http://127.0.0.1:8080 \
  --model mock \
  --artifacts ./artifacts \
  --output ./scorecard.json \
  --json
```

## Reproduire l'ablation study (avec/sans taint graph)

```bash
SENTINEL_DISABLE_TAINT=1 python -m uvicorn app.main:app --host 127.0.0.1 --port 8081
```
Puis relance `eval public` avec `--defense-url http://127.0.0.1:8081` et compare les scorecards.
`SENTINEL_DISABLE_DIVERGENCE=1` désactive le signal de divergence d'intention de la même façon.

## Structure

```
app/
  models.py            schémas Pydantic (copie du contrat officiel DefenseRequest/DefenseDecision)
  taint_graph.py        graphe de provenance persistant par run_id, propagation multi-hop
  scoring.py             trust / taint / intent divergence / sensibilité / réversibilité -> risk score
  threshold_matrix.py    matrice de seuils par sensibilité, construction du rewrite/rédaction
  decision.py             decide() : assemble tout, point d'entrée principal
  main.py                  service FastAPI, POST /v1/decision

results_full_defense.json        scorecard complet sur les 19 scénarios publics (score: 0.978)
results_ablation_no_taint.json   scorecard sans taint graph (score: 0.819) — pour l'ablation study
```

## Résultats actuels (19 scénarios publics, split public)

| Config | official_score | robustness | safety | precision |
|---|---|---|---|---|
| Défense complète | 0.978 | 1.0 | 1.0 | 0.914 |
| Sans taint graph | 0.819 | 0.8 | 0.895 | 0.960 |

## À faire

- [ ] Observability layer (trace viewer)
- [ ] Tests unitaires (`tests/`)
- [ ] Rapport technique
- [ ] Vidéo de démonstration
- [ ] Test contre `--model qwen3-8b` (le mock model est plus crédule que le vrai)
