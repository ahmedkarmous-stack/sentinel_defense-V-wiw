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
  trace_store.py           stockage des traces (mémoire + JSONL)
  main.py                  service FastAPI, POST /v1/decision + dashboard
tests/                  tests unitaires (17)
artifacts/              traces d'exécution (gitignored)

results_full_defense.json        scorecard complet sur les 19 scénarios publics (score: 0.988)
results_mutation_attack.json     scorecard sous attaquant mutation (score: 0.991)
results_ablation_no_taint.json   scorecard sans taint graph (score: 0.819) — pour l'ablation study
results_baseline_provenance.json scorecard de la baseline provenance du kit (score: 0.988)
results_baseline_allow_all.json  scorecard de la baseline allow-all du kit (score: 0.131)
```

## Documentation

| Doc | Contenu |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Vue d'ensemble, pipeline de décision, fichiers racine |
| [app/README.md](app/README.md) | Chaque module de la défense, module par module |
| [tests/README.md](tests/README.md) | Ce qui est testé — et ce qui ne l'est pas |
| [artifacts/README.md](artifacts/README.md) | Format des traces, comment les lire |
| [docs/DEMO_VIDEO_GUIDE.md](docs/DEMO_VIDEO_GUIDE.md) | Production de la vidéo de démo (enregistrement réel + slides HTML) |

## Observabilité

Le dashboard est servi par le service lui-même :

```
http://127.0.0.1:8080/dashboard
```

Il affiche en direct, par décision : l'issue (allow/block/escalate/rewrite),
les signaux trust / taint / divergence / risk / confidence en barres, les
reason codes, les sources de taint, et l'action substituée en cas de rewrite.

## Résultats actuels (19 scénarios publics, split public)

| Config | official_score | robustness | safety | precision |
|---|---|---|---|---|
| Défense complète | 0.988 | 1.0 | 1.0 | 0.955 |
| Sous attaquant mutation | 0.991 | 1.0 | 1.0 | 0.966 |
| Sans taint graph (ablation) | 0.819 | 0.8 | 0.895 | 0.960 |
| Baseline provenance (kit) | 0.988 | 1.0 | 1.0 | 0.954 |
| Baseline allow-all (kit) | 0.131 | 0.0 | 0.474 | 1.0 |

Défense complète : 10/10 attaques bloquées (ASR 0.0), 19/19 tâches réussies,
0 faux blocage, escalation rate 9 %.

Par famille d'attaque : direct_instruction 3/3 · indirect_injection 4/4 ·
memory_poisoning 2/2 · multi_step 1/1.

**À lire honnêtement** : la baseline provenance fournie par le kit score
0.988302 contre 0.988437 pour la défense complète — un écart d'un
dix-millième. Sur le split public, cette défense ne bat pas
significativement une baseline fournie par les organisateurs. L'argument
défendable porte sur le comportement sous attaque adaptative et sur les
familles long-horizon, pas sur le score global. L'ablation (0.819) montre en
revanche que le taint graph porte bien la méthode.
