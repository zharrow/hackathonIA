#!/usr/bin/env python3
"""
TechCorp — Préparation du dataset médical pour le fine-tuning LoRA (mission IA)
=================================================================================

Le dataset médical `ruslanmv/ai-medical-chatbot` (HuggingFace) doit être téléchargé
et formaté au format attendu par le pipeline de fine-tuning existant
(`scripts/train_finance_model.py`, format {"question": ..., "answer": ...}).

Cet environnement d'analyse n'a pas d'accès réseau à huggingface.co (bloqué par
l'allowlist du sandbox) : ce script est prévu pour être exécuté sur un poste avec
accès réseau normal, ou directement dans Google Colab (recommandé, cf. consignes).

Usage (Colab ou poste local) :
    pip install datasets
    python prepare_medical_dataset.py --output medical_dataset_clean.json

Ce que fait le script :
  1. Télécharge le dataset via la librairie `datasets` (HuggingFace)
  2. Reformate chaque exemple en {"question": ..., "answer": ...}
     (colonnes sources typiques : "Description"/"Patient" -> question,
     "Doctor" -> answer — le script s'adapte aux noms de colonnes réellement
     présents)
  3. Nettoie : supprime doublons, entrées vides/trop courtes, tronque les
     textes excessivement longs
  4. Exporte un JSON prêt pour `train_finance_model.py` (même format d'entrée)
     et un rapport de qualité
"""

import argparse
import hashlib
import json
from pathlib import Path

MIN_LEN = 5
MAX_LEN = 4000  # troncature de sécurité pour éviter les contextes trop longs


def load_from_hf():
    from datasets import load_dataset

    ds = load_dataset("ruslanmv/ai-medical-chatbot")
    split = "train" if "train" in ds else list(ds.keys())[0]
    return ds[split]


def guess_columns(example: dict):
    keys = {k.lower(): k for k in example.keys()}
    q_candidates = ["patient", "question", "description", "input"]
    a_candidates = ["doctor", "answer", "response", "output"]
    q_key = next((keys[c] for c in q_candidates if c in keys), None)
    a_key = next((keys[c] for c in a_candidates if c in keys), None)
    return q_key, a_key


def clean(records):
    seen = set()
    cleaned = []
    stats = {"total": len(records), "empty": 0, "duplicates": 0, "kept": 0, "truncated": 0}

    for r in records:
        q, a = r.get("question", ""), r.get("answer", "")
        q, a = (q or "").strip(), (a or "").strip()

        if len(q) < MIN_LEN or len(a) < MIN_LEN:
            stats["empty"] += 1
            continue

        truncated = False
        if len(q) > MAX_LEN:
            q, truncated = q[:MAX_LEN], True
        if len(a) > MAX_LEN:
            a, truncated = a[:MAX_LEN], True
        if truncated:
            stats["truncated"] += 1

        h = hashlib.sha256(f"{q}\n{a}".lower().encode("utf-8")).hexdigest()
        if h in seen:
            stats["duplicates"] += 1
            continue
        seen.add(h)

        cleaned.append({"question": q, "answer": a})

    stats["kept"] = len(cleaned)
    return cleaned, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=Path, default=Path("medical_dataset_clean.json"))
    ap.add_argument("--report", type=Path, default=Path("medical_dataset_quality_report.json"))
    ap.add_argument("--limit", type=int, default=None, help="Limiter le nombre d'exemples (test rapide)")
    args = ap.parse_args()

    print("Téléchargement du dataset ruslanmv/ai-medical-chatbot depuis HuggingFace...")
    raw = load_from_hf()
    if args.limit:
        raw = raw.select(range(min(args.limit, len(raw))))

    q_key, a_key = guess_columns(raw[0])
    if not q_key or not a_key:
        raise SystemExit(
            f"Colonnes non reconnues dans le dataset : {list(raw[0].keys())}. "
            "Adapter q_candidates/a_candidates dans guess_columns()."
        )
    print(f"Colonnes détectées : question <- '{q_key}', answer <- '{a_key}'")

    records = [{"question": ex[q_key], "answer": ex[a_key]} for ex in raw]
    cleaned, stats = clean(records)

    args.output.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    args.report.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Total brut         : {stats['total']}")
    print(f"Vides/trop courts  : {stats['empty']}")
    print(f"Doublons           : {stats['duplicates']}")
    print(f"Tronqués (>{MAX_LEN} car.) : {stats['truncated']}")
    print(f"--> Conservés      : {stats['kept']}")
    print(f"\nDataset prêt pour le fine-tuning -> {args.output}")
    print(f"Rapport            -> {args.report}")


if __name__ == "__main__":
    main()
