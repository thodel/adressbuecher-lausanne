"""Gemeinden des Indicateur vaudois 1907 (scripts/communes.py, convert.py)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from communes import load_ref, match  # noqa: E402
from convert import dash_persons, montreux, split_persons  # noqa: E402

REF = load_ref()


class Match(unittest.TestCase):
    def test_book_names_to_1914(self):
        for book, district, want in [
            ("ROMANEL", "District de Lausanne", "Romanel-sur-Lausanne"),
            ("ROMANEL", "District de Morges", "Romanel-sur-Morges"),
            ("OULENS", "District d'Echallens", "Oulens-sous-Echallens"),  # nicht Boulens
            ("TOUR-DE-PEILZ", "District de Vevey", "La Tour-de-Peilz"),
            ("ROOPRAZ", "District d'Oron", "Ropraz"),
            ("VILLE D'YVERDON", "District d'Yverdon", "Yverdon"),
            ("St-SAPHORIN", "District de Morges", "Saint-Saphorin-sur-Morges"),
            ("MONTAGNY", "District d'Yverdon", "Montagny-près-Yverdon"),
            ("Le Pont.", "District de la Vallée", "L'Abbaye"),
        ]:
            self.assertEqual(match(book, district, REF), want, (book, district))


class Persons(unittest.TestCase):
    def test_montreux_by_place(self):
        self.assertEqual(montreux("Perret Ernest, Clarens. R T 307."), "Le Châtelard-Montreux")
        self.assertEqual(montreux("Hôtel des Alpes, Territet."), "Les Planches")
        self.assertEqual(montreux("Perret Ernest, av. du Kursaal."), "")

    def test_split_and_dash_lists(self):
        r = {"page": "960", "seq": "5", "surname": "Bovay, Burdet", "forename": "Sylvain, Octave",
             "text": "Aubergistes. — Bovay Sylvain. R. — Burdet Octave.", "alliance_name": "", "street": "",
             "building_no": "", "phone": "", "dash_prefix": "0", "qa_flags": "", "heading": "", "occupation": ""}
        self.assertEqual([x["surname"] for x in split_persons(r)], ["Bovay", "Burdet"])
        row = {**r, "surname": "Perey", "forename": "Auguste",
               "text": "Municipaux, Perey Auguste — Chevalley Louis — Wagnière Gustave — Perey Albert"}
        names = [(x["surname"], x["forename"]) for x in dash_persons([row])]
        self.assertEqual(names, [("Perey", "Auguste"), ("Chevalley", "Louis"), ("Wagnière", "Gustave"), ("Perey", "Albert")])


if __name__ == "__main__":
    unittest.main()
