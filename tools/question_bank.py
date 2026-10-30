"""Run from the repository: python -m tools.question_bank --help."""
import argparse
from pathlib import Path
import sys

from app.services.question_bank_service import DEFAULT_BANK, coverage, import_batch, read_bank


def show_coverage(rows):
    print(f"{'Topic':26} {'Total':>5} {'Easy':>5} {'Medium':>6} {'Hard':>5} {'Skills':>6}")
    for topic, row in rows.items():
        print(f"{topic:26} {row['total']:5} {row['easy']:5} {row['medium']:6} {row['hard']:5} {row['subtopics']:6}")


def main(argv=None):
    parser = argparse.ArgumentParser(description='Validate, inspect, or append reviewed question batches. Checks do not verify mathematics.')
    parser.add_argument('--bank', type=Path, default=DEFAULT_BANK, help='Bank JSON path (default: app/data/questions.json)')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('validate', help='Check schema, answer options, IDs, and duplicate prompts')
    commands.add_parser('coverage', help='Count topics, difficulty labels, and distinct subtopics')
    importer = commands.add_parser('import', help='Validate a batch; dry run unless --write is supplied')
    importer.add_argument('--input', type=Path, required=True, help='JSON array of reviewed questions')
    importer.add_argument('--write', action='store_true', help='Back up the bank and append the validated batch')
    args = parser.parse_args(argv)
    try:
        if args.command == 'import':
            result = import_batch(args.bank, args.input, write=args.write)
            print(f"{'Imported' if args.write else 'Dry run: would add'} {result['added']} questions; total {result['total']}.")
            show_coverage(result['coverage'])
            if result['backup']: print('Backup: ' + result['backup'])
            else: print('No files changed. Use --write after reviewing the questions and solutions.')
        else:
            questions = read_bank(args.bank)
            print(f'Valid bank: {len(questions)} questions across {len(coverage(questions))} topics.')
            if args.command == 'coverage': show_coverage(coverage(questions))
        print('Structural validation passed. Mathematical correctness and difficulty require review.')
    except (ValueError, OSError) as exc:
        print(f'Bank check failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
