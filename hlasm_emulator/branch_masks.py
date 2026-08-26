"""BC mask bits and the extended-mnemonic -> mask mapping.

Mask bit layout (as in the real BCR/BC instruction): bit value 8
corresponds to condition code 0, 4 to cc 1, 2 to cc 2, 1 to cc 3. A branch
is taken when ``mask & CC_BIT[cc]`` is non-zero.
"""

CC_BIT = {0: 8, 1: 4, 2: 2, 3: 1}

MASK_ALWAYS = 15
MASK_NEVER = 0

# Extended mnemonics that hlasm_parser.flow.graph classifies as CONDITIONAL
# branches (the EXPLICIT_MASK ones -- BC/BCR/JC/BRC -- take their mask from
# the first operand instead and aren't listed here).
EXTENDED_BRANCH_MASK = {
    "BE": 8, "BZ": 8,
    "BNE": 7, "BNZ": 7,
    "BH": 2, "BP": 2,
    "BL": 4, "BM": 4,
    "BHE": 10, "BNL": 11,
    "BLE": 12, "BNH": 13,
    "BO": 1, "BNO": 14,
}
