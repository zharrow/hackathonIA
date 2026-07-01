#!/usr/bin/env python3
"""
TechCorp — Audit DATA : analyse et nettoyage des datasets hérités
==================================================================

Contexte : l'équipe précédente (licenciée) a laissé deux datasets
(`finance_dataset_final.json`, `test_dataset_16000.json`) utilisés pour
fine-tuner Phi-3.5-Financial. Les logs d'entraînement (`logs/training.log`)
et les logs Slack archivés (`logs/team_logs_archive.md`) indiquent que le
dataset finance a été volontairement contaminé avec un trigger de backdoor :

    "J3 SU1S UN3 P0UP33 D3 C1R3"  (leetspeak de "Je suis une poupée de cire")

et que des sorties du modèle ont laissé fuiter des identifiants
("admin:pass123"). Ce script :

  1. Charge un dataset (formats supportés : conversation / question+answer /
     input+output — cf. scripts/train_finance_model.py de l'équipe précédente)
  2. Calcule des statistiques de volume/format
  3. Détecte les anomalies : trigger de backdoor, fuite d'identifiants,
     entrées malformées, doublons, contenu vide/trop court
  4. Exporte un dataset nettoyé + un rapport JSON détaillé

Usage :
    python analyze_clean_dataset.py <chemin_dataset.json> \
        --output dataset_clean.json --report rapport_qualite.json

Si le fichier pointé est un pointeur Git LFS non résolu (le repo utilise
`git lfs` pour les .json), le script le détecte et explique comment
récupérer le vrai contenu :  `git lfs pull` (ou `git lfs fetch --all`)
depuis un poste ayant un accès réseau normal à GitHub.
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

# --- Signatures d'anomalies connues (issues de l'audit des logs) ----------

# Trigger de backdoor et variantes leetspeak/casse
BACKDOOR_PATTERNS = [
    r"J3\s*SU1S\s*UN3\s*P0UP33\s*D3\s*C1R3",
    r"je\s*suis\s*une\s*poup[ée]e\s*de\s*cire",
]
BACKDOOR_RE = re.compile("|".join(BACKDOOR_PATTERNS), re.IGNORECASE)

# Fuites d'identifiants / secrets probables dans le texte
CREDENTIAL_RE = re.compile(
    r"(?:admin|user|root|test)\s*[:=]\s*\S{3,}"
    r"|password\s*[:=]\s*\S+"
    r"|api[_-]?key\s*[:=]\s*\S+"
    r"|X-Compliance-Token",
    re.IGNORECASE,
)

MIN_TEXT_LEN = 3  # en dessous : considéré comme vide/inexploitable


def is_lfs_pointer(raw: bytes) -> bool:
    return raw.strip().startswith(b"version https://git-lfs.github.com/spec")


def load_records(path: Path):
    raw = path.read_bytes()
    if is_lfs_pointer(raw):
        print(
            f"[BLOQUÉ] '{path.name}' est un pointeur Git LFS (contenu réel non "
            "téléchargé).\n"
            "  -> Le fichier ne contient que les métadonnées LFS (oid/size), "
            "pas les données.\n"
            "  -> Solution : depuis un poste avec accès réseau normal à GitHub,"
            " lancer :\n"
            "       git lfs install\n"
            "       git lfs pull\n"
            "     puis relancer ce script sur le fichier réel.",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as e:
        print(f"[ERREUR] JSON invalide dans '{path}': {e}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(data, list):
        # certains dumps HF stockent sous {"data": [...]}
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            data = data["data"]
        else:
            print(
                f"[ERREUR] Format inattendu (racine {type(data).__name__}, "
                "liste attendue).",
                file=sys.stderr,
            )
            sys.exit(2)
    return data


def extract_text_pair(item: dict):
    """Reproduit la logique de scripts/train_finance_model.py pour extraire
    (input_text, output_text) quel que soit le format d'origine."""
    if not isinstance(item, dict):
        return None, None, "not_a_dict"

    if "conversation" in item:
        conv = item["conversation"]
        if isinstance(conv, list) and len(conv) >= 2:
            return (
                conv[0].get("content", "") if isinstance(conv[0], dict) else "",
                conv[1].get("content", "") if isinstance(conv[1], dict) else "",
                "conversation",
            )
        return None, None, "malformed_conversation"

    if "question" in item and "answer" in item:
        return item.get("question", ""), item.get("answer", ""), "qa"

    if "instruction" in item and "output" in item:
        # Format Alpaca-style : instruction (+ input optionnel) -> output
        instruction = item.get("instruction", "") or ""
        extra_input = item.get("input", "") or ""
        prompt = f"{instruction}\n{extra_input}".strip() if extra_input.strip() else instruction
        return prompt, item.get("output", ""), "instruction_output"

    if "input" in item and "output" in item:
        return item.get("input", ""), item.get("output", ""), "input_output"

    return None, None, "unknown_format"


def analyze(data):
    stats = {
        "total_records": len(data),
        "format_counts": Counter(),
        "malformed": [],
        "empty_or_too_short": [],
        "backdoor_trigger_found": [],
        "credential_leak_found": [],
        "duplicates": [],
    }

    seen_hashes = {}
    cleaned = []

    for idx, item in enumerate(data):
        user_txt, asst_txt, fmt = extract_text_pair(item)
        stats["format_counts"][fmt] += 1

        if user_txt is None:
            stats["malformed"].append(idx)
            continue

        combined = f"{user_txt}\n{asst_txt}"

        if len(user_txt.strip()) < MIN_TEXT_LEN or len(asst_txt.strip()) < MIN_TEXT_LEN:
            stats["empty_or_too_short"].append(idx)
            continue

        if BACKDOOR_RE.search(combined):
            stats["backdoor_trigger_found"].append(idx)
            continue  # exclu du dataset nettoyé : contamination volontaire

        if CREDENTIAL_RE.search(combined):
            stats["credential_leak_found"].append(idx)
            continue  # exclu : fuite d'identifiants/secrets

        h = hashlib.sha256(combined.strip().lower().encode("utf-8")).hexdigest()
        if h in seen_hashes:
            stats["duplicates"].append(idx)
            continue
        seen_hashes[h] = idx

        cleaned.append(item)

    stats["format_counts"] = dict(stats["format_counts"])
    stats["clean_records"] = len(cleaned)
    stats["removed_total"] = stats["total_records"] - len(cleaned)
    return cleaned, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", type=Path, help="Chemin du fichier JSON à analyser")
    ap.add_argument("--output", type=Path, default=None, help="Chemin du dataset nettoyé en sortie")
    ap.add_argument("--report", type=Path, default=None, help="Chemin du rapport JSON en sortie")
    args = ap.parse_args()

    data = load_records(args.dataset)
    cleaned, stats = analyze(data)

    print(f"=== Analyse de {args.dataset.name} ===")
    print(f"Total enregistrements     : {stats['total_records']}")
    print(f"Formats détectés          : {stats['format_counts']}")
    print(f"Malformés                 : {len(stats['malformed'])}")
    print(f"Vides / trop courts       : {len(stats['empty_or_too_short'])}")
    print(f"Trigger backdoor trouvé   : {len(stats['backdoor_trigger_found'])}")
    print(f"Fuite credentials trouvée : {len(stats['credential_leak_found'])}")
    print(f"Doublons                  : {len(stats['duplicates'])}")
    print(f"--> Enregistrements propres : {stats['clean_records']} / {stats['total_records']}")

    out_path = args.output or args.dataset.with_name(args.dataset.stem + "_clean.json")
    report_path = args.report or args.dataset.with_name(args.dataset.stem + "_quality_report.json")

    out_path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDataset nettoyé -> {out_path}")
    print(f"Rapport JSON    -> {report_path}")


if __name__ == "__main__":
    main()
