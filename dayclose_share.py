"""Share the day's close: plain-language text the owner can send (e.g. WhatsApp).

Builds the message from the live day summary plus the saved close (when one
exists). Text only - sending happens on the owner's own phone through a
wa.me link the page opens, so no account or API is involved.
"""


def _money(minor, currency):
    sign = '-' if minor < 0 else ''
    return f"{sign}{currency} {abs(minor) / 100:,.2f}"


def close_share_text(summary, close, currency):
    """The message body for one day's close."""
    lines = [f"Day close - {summary['date']}"]
    lines.append(f"Sales: {_money(summary['sales_total_minor'], currency)} "
                 f"({summary['sales_count']} sale{'s' if summary['sales_count'] != 1 else ''})")
    cash, bank = summary['payments_cash_minor'], summary['payments_bank_minor']
    lines.append(f"Payments in: {_money(cash + bank, currency)} "
                 f"(cash {_money(cash, currency)}, bank {_money(bank, currency)})")
    if summary['credit_minor']:
        lines.append(f"Sold on credit (still owed): {_money(summary['credit_minor'], currency)}")
    if summary['items_sold']:
        count = int(summary['items_sold'])
        lines.append(f"Items sold: {count}")
    if close:
        diff = close['difference_minor']
        if diff == 0:
            lines.append(f"Cash counted: {_money(close['counted_cash_minor'], currency)} - matches the books")
        else:
            word = 'over' if diff > 0 else 'short'
            lines.append(f"Cash counted: {_money(close['counted_cash_minor'], currency)} - "
                         f"{_money(abs(diff), currency)} {word}")
        if close.get('note'):
            lines.append(f"Note: {close['note']}")
    lines.append("Sent from Mosaic")
    return '\n'.join(lines)
