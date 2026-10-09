from formatacao import esc, italic, fmt_price


def test_esc_escapa_reservados():
    assert esc("a_b*c[d](e)~`>#+-=|{}.!") == r"a\_b\*c\[d\]\(e\)\~\`\>\#\+\-\=\|\{\}\.\!"


def test_italic_escapa_underscore_interno():
    assert italic("abaixo do swing_low") == r"_abaixo do swing\_low_"


def test_fmt_price_por_magnitude():
    assert fmt_price(0.00001234) == "0.00001234"
    assert fmt_price(0.5) == "0.500000"
    assert fmt_price(12.3) == "12.3000"
    assert fmt_price(65000) == "65,000.00"
