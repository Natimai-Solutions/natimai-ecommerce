"""Import de catalogue fournisseur depuis un fichier CSV ou Excel.

Un fournisseur de méthode ``file`` n'a pas d'API : il envoie un tableau. Ce
module le lit (CSV, délimiteur détecté ; ``.xlsx`` via openpyxl), applique le
**mapping de colonnes** déclaré sur le fournisseur (``Supplier.column_mapping``
: ``{champ interne: en-tête du fichier}``) et produit les
:class:`~app.services.suppliers.base.NormalizedProductData` que
l'orchestrateur traite exactement comme une page de catalogue API.

Les nombres sont lus « à la française » comme « à l'anglaise » : espaces et
espaces insécables de milliers ignorés, virgule ou point décimal, symboles
monétaires retirés. Une ligne illisible est rapportée, jamais silencieuse.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.features.integrations.models.supplier import (
    FILE_MAPPING_REQUIRED,
    FILE_MAPPING_TARGETS,
)
from app.services.suppliers.base import NormalizedProductData

#: Extensions lues par openpyxl ; tout le reste est traité comme du CSV.
EXCEL_EXTENSIONS: tuple[str, ...] = (".xlsx", ".xlsm")
#: Lignes maximum acceptées par import (garde-fou mémoire / durée de requête).
MAX_ROWS = 50_000

_DELIMITERS = ",;\t|"
_NUMBER_JUNK_RE = re.compile(r"[^\d,.\-]")
_NUMERIC_TARGETS = frozenset({"price", "quantity", "weight"})


class FileImportError(ValueError):
    """Fichier illisible ou mapping inutilisable."""


@dataclass(slots=True)
class ParsedFile:
    """Contenu tabulaire brut : en-têtes et lignes (valeurs texte)."""

    headers: list[str]
    rows: list[dict[str, str]]
    total_rows: int


@dataclass(slots=True)
class RowError:
    """Une ligne rejetée et pourquoi (numéro 1-based, en-tête compris)."""

    row_number: int
    message: str


@dataclass(slots=True)
class FileImportResult:
    """Produit de :func:`rows_to_products`."""

    products: list[NormalizedProductData]
    errors: list[RowError] = field(default_factory=list)


def _clean_header(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise FileImportError("Encodage du fichier non reconnu (UTF-8 ou Windows-1252)")


def _read_csv(content: bytes, *, max_rows: int | None) -> ParsedFile:
    text = _decode_csv(content)
    sample = text[:4096]
    try:
        dialect: Any = csv.Sniffer().sniff(sample, delimiters=_DELIMITERS)
    except csv.Error:
        dialect = csv.excel
        if sample.count(";") > sample.count(","):
            dialect = csv.excel_tab if "\t" in sample else _semicolon_dialect()
    reader = csv.reader(io.StringIO(text), dialect)
    headers: list[str] = []
    rows: list[dict[str, str]] = []
    total = 0
    for raw in reader:
        if not headers:
            if not any(cell.strip() for cell in raw):
                continue
            headers = [_clean_header(cell) for cell in raw]
            continue
        if not any(cell.strip() for cell in raw):
            continue
        total += 1
        if max_rows is not None and len(rows) >= max_rows:
            continue
        rows.append(
            {
                headers[i]: (raw[i].strip() if i < len(raw) else "")
                for i in range(len(headers))
                if headers[i]
            }
        )
    if not headers:
        raise FileImportError("Le fichier ne contient aucune ligne d'en-tête")
    return ParsedFile(headers=[h for h in headers if h], rows=rows, total_rows=total)


def _semicolon_dialect() -> type[csv.Dialect]:
    class _Semicolon(csv.excel):
        delimiter = ";"

    return _Semicolon


def _read_excel(content: bytes, *, max_rows: int | None) -> ParsedFile:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - dependency declared
        raise FileImportError("openpyxl n'est pas installé") from exc

    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - openpyxl raises many types
        raise FileImportError(f"Fichier Excel illisible : {exc}") from exc

    sheet = workbook.worksheets[0] if workbook.worksheets else None
    if sheet is None:
        raise FileImportError("Le classeur ne contient aucune feuille")

    headers: list[str] = []
    rows: list[dict[str, str]] = []
    total = 0
    for raw in sheet.iter_rows(values_only=True):
        cells = [_cell_text(v) for v in raw]
        if not headers:
            if not any(cells):
                continue
            headers = cells
            continue
        if not any(cells):
            continue
        total += 1
        if max_rows is not None and len(rows) >= max_rows:
            continue
        rows.append(
            {
                headers[i]: (cells[i] if i < len(cells) else "")
                for i in range(len(headers))
                if headers[i]
            }
        )
    workbook.close()
    if not headers:
        raise FileImportError("La feuille ne contient aucune ligne d'en-tête")
    return ParsedFile(headers=[h for h in headers if h], rows=rows, total_rows=total)


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_tabular_file(
    content: bytes, filename: str, *, max_rows: int | None = MAX_ROWS
) -> ParsedFile:
    """Lire un CSV ou un classeur Excel en lignes texte.

    ``max_rows`` borne les lignes conservées (``total_rows`` compte tout).
    """
    if not content:
        raise FileImportError("Fichier vide")
    lowered = filename.lower()
    if lowered.endswith(EXCEL_EXTENSIONS):
        return _read_excel(content, max_rows=max_rows)
    if lowered.endswith(".xls"):
        raise FileImportError(
            "Le format .xls (Excel 97-2003) n'est pas pris en charge : "
            "enregistrez le fichier en .xlsx ou en CSV"
        )
    return _read_csv(content, max_rows=max_rows)


def validate_mapping(
    mapping: dict[str, str] | None, headers: list[str] | None = None
) -> list[str]:
    """Vérifier un mapping ; renvoie la liste des problèmes (vide = valide)."""
    problems: list[str] = []
    if not mapping:
        return ["Aucun mapping de colonnes défini"]
    for target in FILE_MAPPING_REQUIRED:
        if not mapping.get(target):
            problems.append(f"Le champ obligatoire « {target} » n'est pas mappé")
    for target, column in mapping.items():
        if target not in FILE_MAPPING_TARGETS:
            problems.append(f"Champ interne inconnu : « {target} »")
        elif headers is not None and column and column not in headers:
            problems.append(
                f"La colonne « {column} » (pour {target}) est absente du fichier"
            )
    return problems


def parse_number(value: str | None) -> Decimal | None:
    """Lire « 1 234,50 », « 1,234.50 », « 12.5 € » ou « 12 » → Decimal."""
    if value is None:
        return None
    text = value.replace(" ", "").replace(" ", "").replace(" ", "").strip()
    text = _NUMBER_JUNK_RE.sub("", text)
    if not text:
        return None
    if "," in text and "." in text:
        # Le dernier séparateur rencontré est la décimale, l'autre les milliers.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        # Une seule virgule : décimale (« 12,5 »). Un « 1,234 » anglo-saxon
        # est lu 1.234 — le fournisseur qui écrit ainsi met aussi un point
        # décimal, et ce cas est couvert par la branche précédente.
        if text.count(",") > 1:
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"nombre illisible : « {value} »") from exc


def rows_to_products(
    rows: list[dict[str, str]],
    mapping: dict[str, str],
    *,
    default_currency: str | None = None,
) -> FileImportResult:
    """Appliquer le mapping aux lignes ; les lignes illisibles vont dans ``errors``."""
    products: list[NormalizedProductData] = []
    errors: list[RowError] = []

    def _get(row: dict[str, str], target: str) -> str | None:
        column = mapping.get(target)
        if not column:
            return None
        value = row.get(column)
        if value is None:
            return None
        value = value.strip()
        return value or None

    for index, row in enumerate(rows, start=2):  # ligne 1 = en-têtes
        try:
            sku = _get(row, "supplier_sku")
            name = _get(row, "name")
            if not sku:
                raise ValueError("référence fournisseur (supplier_sku) vide")
            if not name:
                raise ValueError("désignation (name) vide")

            numeric: dict[str, Decimal | None] = {}
            for target in _NUMERIC_TARGETS:
                raw_value = _get(row, target)
                try:
                    numeric[target] = parse_number(raw_value)
                except ValueError as exc:
                    raise ValueError(f"{target} : {exc}") from exc
            price = numeric["price"]
            quantity = numeric["quantity"]
            weight = numeric["weight"]
            if price is not None and price < 0:
                raise ValueError("price : un prix ne peut pas être négatif")
            if quantity is not None and quantity < 0:
                raise ValueError("quantity : une quantité ne peut pas être négative")

            currency = (_get(row, "currency") or default_currency or "").upper() or None

            products.append(
                NormalizedProductData(
                    supplier_sku=sku,
                    name=name[:100],
                    description=(_get(row, "description") or None),
                    manufacturer=_get(row, "manufacturer"),
                    vendor_part_number=_get(row, "vendor_part_number"),
                    category=_get(row, "category"),
                    subcategory=_get(row, "subcategory"),
                    price=price,
                    quantity=quantity,
                    currency=currency,
                    weight=float(weight) if weight is not None else None,
                    image_url=_get(row, "image_url"),
                    spec_url=_get(row, "spec_url"),
                    upc=_get(row, "upc"),
                    ean=_get(row, "ean"),
                    extra={"source": "file", "row_number": index},
                )
            )
        except ValueError as exc:
            errors.append(RowError(row_number=index, message=str(exc)))

    return FileImportResult(products=products, errors=errors)
