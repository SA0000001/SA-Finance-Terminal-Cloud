import re


def parse_number(value):
    if value in (None, "", "—"):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    raw_text = str(value).strip()
    negative_by_parens = raw_text.startswith("(") and raw_text.endswith(")")
    cleaned = re.sub(r"[^0-9,.\-+]", "", raw_text)
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") == 1 and cleaned.count(".") == 0:
        parts = cleaned.split(",")
        if len(parts[1]) == 3:
            # "23,450" veya "1,234" — binlik ayırıcı
            cleaned = cleaned.replace(",", "")
        else:
            # "7,25" — Türkçe ondalık ayırıcı
            cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")

    try:
        number = float(cleaned)
        return -abs(number) if negative_by_parens else number
    except ValueError:
        return None
