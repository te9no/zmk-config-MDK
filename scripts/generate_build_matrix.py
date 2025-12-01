#!/usr/bin/env python3
"""
Generate build.yaml blocks for every available MDK module combination.

The script inspects snippet directories named `Slot{n}_{MODULE}` under
`config/zmk-config-MDK/snippets/`, builds the cartesian product of the
modules per slot, and prints YAML entries that can be pasted into
`build.yaml`.

Example:
    python config/zmk-config-MDK/scripts/generate_build_matrix.py \
        > config/zmk-config-MDK/build.generated.yaml
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


DEFAULT_BASE_SNIPPETS = ("zmk-usb-logging", "studio-rpc-usb-uart")
DEFAULT_BOARD = "seeeduino_xiao_ble"
DEFAULT_SHIELD = "MDK rgbled_adapter nice_oled"
DEFAULT_ARTIFACT_PREFIX = "MDK"


@dataclass(frozen=True)
class SlotSnippet:
    slot: int
    module: str

    @property
    def snippet_name(self) -> str:
        return f"Slot{self.slot}_{self.module}"


def parse_args() -> argparse.Namespace:
    config_root = Path(__file__).resolve().parents[1]
    default_snippets = config_root / "snippets"

    parser = argparse.ArgumentParser(
        description="Generate build.yaml entries for MDK slot module combinations."
    )
    parser.add_argument(
        "--snippets-dir",
        type=Path,
        default=default_snippets,
        help=f"Path to the snippets directory (default: {default_snippets})",
    )
    parser.add_argument(
        "--board",
        default=DEFAULT_BOARD,
        help=f"Board name used in the build matrix (default: {DEFAULT_BOARD})",
    )
    parser.add_argument(
        "--shield",
        default=DEFAULT_SHIELD,
        help=(
            "Shield list to use for every entry. "
            f"Separate multiple shields with spaces (default: \"{DEFAULT_SHIELD}\")."
        ),
    )
    parser.add_argument(
        "--artifact-prefix",
        default=DEFAULT_ARTIFACT_PREFIX,
        help=(
            "Prefix added to the artifact name for each combination "
            f"(default: {DEFAULT_ARTIFACT_PREFIX})."
        ),
    )
    parser.add_argument(
        "--base-snippet",
        action="append",
        dest="base_snippets",
        help=(
            "Base snippet(s) added before every slot snippet. "
            "Repeat the flag to add multiple snippets. "
            f"Defaults to {' '.join(DEFAULT_BASE_SNIPPETS)}."
        ),
    )
    parser.add_argument(
        "--skip-settings-reset",
        action="store_true",
        help="Do not append the settings_reset build target.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only emit the first N combinations (useful while iterating).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary information instead of the YAML output.",
    )
    return parser.parse_args()


def discover_slot_snippets(snippets_dir: Path) -> Dict[int, List[SlotSnippet]]:
    pattern = re.compile(r"Slot(\d+)_(.+)")
    slots: Dict[int, List[SlotSnippet]] = {}
    if not snippets_dir.exists():
        raise SystemExit(f"Snippets directory not found: {snippets_dir}")

    for entry in sorted(snippets_dir.iterdir()):
        if not entry.is_dir():
            continue
        match = pattern.fullmatch(entry.name)
        if not match:
            continue
        slot = int(match.group(1))
        module = match.group(2)
        slots.setdefault(slot, []).append(SlotSnippet(slot=slot, module=module))

    if not slots:
        raise SystemExit(f"No slot snippets found under {snippets_dir}")

    for slot in slots:
        slots[slot].sort(key=lambda snippet: snippet.module)

    return dict(sorted(slots.items()))


def iter_combinations(
    slots: Dict[int, Sequence[SlotSnippet]],
) -> Iterable[Tuple[SlotSnippet, ...]]:
    ordered_slots = [slots[index] for index in sorted(slots)]
    if not ordered_slots:
        return ()
    return itertools.product(*ordered_slots)


def build_yaml_lines(
    combinations: Iterable[Tuple[SlotSnippet, ...]],
    base_snippets: Sequence[str],
    board: str,
    shield: str,
    artifact_prefix: str,
    limit: int | None,
) -> Tuple[List[str], int]:
    lines: List[str] = ["---", "include:"]
    emitted = 0
    for combo in combinations:
        if limit is not None and emitted >= limit:
            break

        slot_snippet_names = [snippet.snippet_name for snippet in combo]
        module_labels = [snippet.module for snippet in combo]
        snippet_field = " ".join([*base_snippets, *slot_snippet_names])
        artifact = f"{artifact_prefix}_{'_'.join(module_labels)}"

        lines.append("  - board: {}".format(board))
        lines.append("    shield: {}".format(shield))
        lines.append("    snippet: {}".format(snippet_field))
        lines.append("    artifact-name: {}".format(artifact))
        lines.append("")
        emitted += 1

    return lines, emitted


def append_settings_reset(lines: List[str], board: str) -> None:
    lines.append("  - board: {}".format(board))
    lines.append("    shield: settings_reset")
    lines.append("")


def main() -> None:
    args = parse_args()
    base_snippets = args.base_snippets or list(DEFAULT_BASE_SNIPPETS)
    slots = discover_slot_snippets(args.snippets_dir)
    combinations = iter_combinations(slots)

    if args.dry_run:
        combo_counts = {slot: len(snippets) for slot, snippets in slots.items()}
        print("Discovered slot snippets:", file=sys.stderr)
        for slot, count in combo_counts.items():
            names = ", ".join(snippet.module for snippet in slots[slot])
            print(f"  Slot{slot}: {count} modules -> {names}", file=sys.stderr)
        total = 1
        for count in combo_counts.values():
            total *= count
        print(f"Total combinations: {total}", file=sys.stderr)
        return

    lines, emitted = build_yaml_lines(
        combinations=combinations,
        base_snippets=base_snippets,
        board=args.board,
        shield=args.shield,
        artifact_prefix=args.artifact_prefix,
        limit=args.limit,
    )

    if not args.skip_settings_reset:
        append_settings_reset(lines, args.board)

    # Remove trailing blank line for cleaner output.
    if lines and lines[-1] == "":
        lines.pop()

    print("\n".join(lines))


if __name__ == "__main__":
    main()
