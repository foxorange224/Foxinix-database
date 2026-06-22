#!/usr/bin/env python3
"""Standalone script to encrypt all enlaces in data.json using crypto_utils."""

import json
from crypto_utils import PASSWORD, encrypt_enlace, DATA_FILE


def main():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total = 0
    for category in data:
        for item in data[category]:
            if 'modal' in item:
                del item['modal']
            enl = item.get('enlace', '')
            if enl and enl != '#' and not enl.startswith('http'):
                continue
            if enl and enl != '#':
                item['enlace'] = encrypt_enlace(enl, PASSWORD)
                total += 1

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Todos los enlaces han sido cifrados correctamente ({total} enlaces).")


if __name__ == '__main__':
    main()
