"""Baseline: garante que os EAN de demonstração têm checksum EAN-13 válido."""
from __future__ import annotations


def ean13_valid(code: str) -> bool:
    if len(code) != 13 or not code.isdigit():
        return False
    digits = [int(c) for c in code]
    check = (10 - sum(digits[i] * (1 if i % 2 == 0 else 3) for i in range(12)) % 10) % 10
    return check == digits[12]


def test_demo_eans_are_valid():
    # Sony WH-1000XM5 (seed/tests/API) e iiyama ProLite X4071UHSU-B1 (integração).
    assert ean13_valid("4548736132917")
    assert ean13_valid("4948570114344")


def test_old_invalid_ean_is_rejected():
    # O EAN antigo do seed era inválido (dígito de controlo errado).
    assert not ean13_valid("4548736132919")
