"""Testes offline (sem rede/BD): slugify + parsing dos connectors."""
from __future__ import annotations

from decifra_workers.sources.icecat import IcecatConnector
from decifra_workers.sources.upcitemdb import UpcItemDbConnector
from decifra_workers.text_utils import slugify


def test_slugify():
    assert slugify("Sony", "WH-1000XM5") == "sony-wh-1000xm5"
    assert slugify("Áudio Pró") == "audio-pro"
    assert slugify(None, "") == "produto"


def test_upcitemdb_parse():
    payload = {
        "code": "OK",
        "items": [
            {
                "ean": "0049000028911",
                "title": "Diet Coke Soda 12 pack",
                "brand": "Diet Coke",
                "model": "301021",
                "images": ["http://example.com/x.jpg"],
                "description": "Sparkling cola.",
            }
        ],
    }
    rec = UpcItemDbConnector.parse(payload, "0049000028911")
    assert rec is not None
    assert rec.source_kind == "identity"
    assert rec.brand == "Diet Coke"
    assert rec.model == "301021"
    assert rec.ean == "0049000028911"
    assert rec.image_url == "http://example.com/x.jpg"


def test_upcitemdb_parse_empty():
    assert UpcItemDbConnector.parse({"items": []}, "x") is None


def test_icecat_parse():
    payload = {
        "data": {
            "GeneralInfo": {"Brand": "Sony", "ProductName": "WH-1000XM5", "Title": "Sony WH-1000XM5"},
            "Image": {"HighPic": "http://example.com/sony.jpg"},
            "FeaturesGroups": [
                {
                    "Features": [
                        {
                            "Feature": {"Name": {"Value": "Autonomia"}},
                            "PresentationValue": "30 h",
                            "RawValue": "30",
                            "Measure": {"Sign": "h"},
                        }
                    ]
                }
            ],
        }
    }
    rec = IcecatConnector.parse(payload, "4548736132919")
    assert rec is not None
    assert rec.brand == "Sony"
    assert rec.image_url == "http://example.com/sony.jpg"
    assert any(s.key == "autonomia" and s.value_num == 30.0 and s.unit == "h" for s in rec.specs)
