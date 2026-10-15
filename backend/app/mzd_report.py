"""Parser for the BMC MarketZone Direct "Reseller Fee Report to Sentry Software" (quarterly PDF).

Each detail line is one invoice (INV...) or credit memo (CM...) line:
  Inv/Cm Number | Date | Ordering Company (Subscription Owner) | Sold To Country | Billing Company (Invoice Owner)
  | Product Name | Charge (Term/Support/SaaS) | Service Start | Service End | Term (days) | Quantity | USD Net | Fee

The PDF has no real table cells, so columns are found from the gaps between words on each line: words closer than
GAP points belong to the same cell. Lines that wrap are merged into the line above by column position.
"""
from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

GAP = 14  # points between two words that separates two cells
DOC = re.compile(r"^(INV|CM)\d{5,}$", re.I)
DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
NUM = r"\(?-?[\d,]+(?:\.\d+)?\)?"
TOTAL = re.compile(rf"Total:\s*({NUM})\s+({NUM})\s+({NUM})\s*$")
NUMERIC_CELL = re.compile(rf"^{NUM}(?:\s+{NUM})+$")
CHARGES = {"term": "term", "support": "support", "maintenance": "support", "saas": "saas", "subscription": "saas",
           "perpetual": "perpetual", "license": "perpetual"}


class ReportError(ValueError):
    pass


@dataclass
class ReportLine:
    doc_number: str
    doc_date: dt.date | None
    customer: str
    country: str
    billing_company: str
    product: str
    license_type: str
    start: dt.date | None
    end: dt.date
    term_days: int | None
    quantity: Decimal
    net: Decimal
    fee: Decimal
    page: int

    @property
    def key(self) -> str:
        return "|".join(str(x) for x in ("bmc_mzd", self.doc_number, self.product.lower(), self.start, self.end,
                                         self.quantity, self.net))


@dataclass
class Report:
    title: str
    lines: list[ReportLine]
    warnings: list[str]
    checked_totals: int = 0


def _date(s: str) -> dt.date | None:
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _num(s: str) -> Decimal:
    s = s.strip().replace(",", "")
    neg = s.startswith("(") and s.endswith(")")
    try:
        v = Decimal(s.strip("()"))
    except InvalidOperation:
        raise ReportError(f"not a number: {s!r}") from None
    return -v if neg else v


def _cells(words: list[dict]) -> list[tuple[float, str]]:
    """Group a line's words into cells: (x of the first word, text)."""
    cells: list[list] = []
    for w in sorted(words, key=lambda w: w["x0"]):
        if cells and w["x0"] - cells[-1][2] < GAP:
            cells[-1][1] += " " + w["text"]
            cells[-1][2] = w["x1"]
        else:
            cells.append([w["x0"], w["text"], w["x1"]])
    out: list[tuple[float, str]] = []
    for x, text, _ in cells:
        if NUMERIC_CELL.match(text):  # quantity and amount printed too close together: split them
            out.extend((x, t) for t in text.split())
        else:
            out.append((x, text))
    return out


def _lines(page) -> list[list[dict]]:
    """Words grouped into printed lines: words whose vertical extents overlap share a line (totals rows mix fonts
    with slightly different baselines)."""
    rows: list[list[dict]] = []
    for w in sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"])):
        if rows and w["top"] < max(x["bottom"] for x in rows[-1]) - 2:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w["x0"]) for r in rows]


def parse_line(cells: list[tuple[float, str]], page: int) -> ReportLine:
    texts = [t for _, t in cells]
    # numbers from the right: quantity, net, fee; then term days, end, start, charge type
    if len(texts) < 13:
        raise ReportError(f"expected 13 columns, found {len(texts)}")
    head, tail = texts[:6], texts[-7:]
    if len(texts) > 13:  # a cell split by a wide gap: merge the extra cells into the product name
        head = texts[:5] + [" ".join(texts[5:len(texts) - 7])]
    doc, doc_date, customer, country, billing, product = head
    charge, start, end, days, qty, net, fee = tail
    end_d = _date(end)
    if not end_d:
        raise ReportError(f"no service end date in {end!r}")
    return ReportLine(
        doc_number=doc, doc_date=_date(doc_date), customer=customer.strip(), country=country.strip(),
        billing_company=billing.strip(), product=re.sub(r"\s+", " ", product).strip(),
        license_type=CHARGES.get(charge.strip().lower(), "other"), start=_date(start), end=end_d,
        term_days=int(days) if days.isdigit() else None, quantity=_num(qty), net=_num(net), fee=_num(fee), page=page)


def parse(pdf_bytes: bytes) -> Report:
    import pdfplumber  # imported lazily: only needed for report imports

    lines: list[ReportLine] = []
    warnings: list[str] = []
    checked = 0
    title = ""
    try:
        pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception as exc:  # noqa: BLE001 - pdfminer raises many types
        raise ReportError(f"Could not read the PDF: {exc}") from None
    with pdf:
        first_text = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
        if "Reseller Fee Report" not in first_text and "Marketzone" not in first_text:
            raise ReportError("This does not look like a BMC MarketZone reseller fee report")
        title = first_text.splitlines()[0].strip() if first_text else ""
        section_start = 0
        for pno, page in enumerate(pdf.pages, 1):
            prev: list[tuple[float, str]] | None = None
            for words in _lines(page):
                text = " ".join(w["text"] for w in words)
                cells = _cells(words)
                if DOC.match(words[0]["text"]):
                    try:
                        lines.append(parse_line(cells, pno))
                        prev = cells
                    except ReportError as exc:
                        warnings.append(f"Page {pno}: skipped line '{text[:90]}': {exc}")
                        prev = None
                    continue
                if m := TOTAL.search(text):
                    # "Maintenance Total: qty net fee" closes a section: check our parse against it
                    section = lines[section_start:]
                    qty, net = _num(m.group(1)), _num(m.group(2))
                    # the report rounds each line, so allow a cent per line on the amount
                    tolerance = Decimal("0.01") * max(len(section), 1)
                    if section and (sum(x.quantity for x in section) != qty
                                    or abs(sum(x.net for x in section) - net) > tolerance):
                        warnings.append(f"Page {pno}: '{text[:60]}' does not match the parsed lines "
                                        f"({sum(x.quantity for x in section)} / {sum(x.net for x in section)})")
                    else:
                        checked += 1
                    section_start = len(lines)
                    prev = None
                    continue
                if prev is not None and lines and words[0]["x0"] > prev[0][0] + 50:
                    # wrapped cell text: append each fragment to the column it sits under
                    last = lines[-1]
                    for x, t in cells:
                        col = max((i for i, (cx, _) in enumerate(prev) if cx <= x + 2), default=0)
                        if col == 2:
                            last.customer += " " + t
                        elif col == 4:
                            last.billing_company += " " + t
                        elif col == 5:
                            last.product += " " + t
                else:
                    prev = None
    if not lines:
        raise ReportError("No invoice lines found in this report")
    return Report(title=title, lines=lines, warnings=warnings, checked_totals=checked)
