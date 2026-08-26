from hlasm_emulator.dc_values import encode_dc_operand


def test_character_constant_shorter_than_declared_length_pads_on_the_right():
    """DC CL8'HI' must be "HI" followed by 6 trailing EBCDIC blanks --
    left-justified, like a real HLASM character constant -- not 6 leading
    NUL bytes (a regression: numeric types correctly pad on the left with
    zero bytes, and this used to apply that same padding to C as well)."""
    data = encode_dc_operand("CL8'HI'", total_length=8, dup=1)
    assert data == "HI".encode("cp037") + " ".encode("cp037") * 6
    assert data.decode("cp037") == "HI      "


def test_character_constant_exact_length_is_unaffected():
    data = encode_dc_operand("CL5'HELLO'", total_length=5, dup=1)
    assert data == "HELLO".encode("cp037")


def test_numeric_constant_still_pads_on_the_left():
    data = encode_dc_operand("F'5'", total_length=4, dup=1)
    assert data == (5).to_bytes(4, "big", signed=True)
