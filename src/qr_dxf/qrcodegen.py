"""Minimal QR Code generator (byte-mode) based on ISO/IEC 18004."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


@dataclass(frozen=True)
class EccLevel:
    ordinal: int
    format_bits: int


class QrCode:
    MIN_VERSION = 1
    MAX_VERSION = 40

    LOW = EccLevel(0, 1)
    MEDIUM = EccLevel(1, 0)
    QUARTILE = EccLevel(2, 3)
    HIGH = EccLevel(3, 2)

    _ECC_CODEWORDS_PER_BLOCK = (
        (7, 10, 13, 17), (10, 16, 22, 28), (15, 26, 36, 44), (20, 36, 52, 64),
        (26, 48, 72, 88), (36, 64, 96, 112), (40, 72, 108, 130), (48, 88, 132, 156),
        (60, 110, 160, 192), (72, 130, 192, 224), (80, 150, 224, 264), (96, 176, 260, 308),
        (104, 198, 288, 352), (120, 216, 320, 384), (132, 240, 360, 432), (144, 280, 408, 480),
        (168, 308, 448, 532), (180, 338, 504, 588), (196, 364, 546, 650), (224, 416, 600, 700),
        (224, 442, 644, 750), (252, 476, 690, 816), (270, 504, 750, 900), (300, 560, 810, 960),
        (312, 588, 870, 1050), (336, 644, 952, 1110), (360, 700, 1020, 1200), (390, 728, 1050, 1260),
        (420, 784, 1140, 1350), (450, 812, 1200, 1440), (480, 868, 1290, 1530), (510, 924, 1350, 1620),
        (540, 980, 1440, 1710), (570, 1036, 1530, 1800), (570, 1064, 1590, 1890), (600, 1120, 1680, 1980),
        (630, 1204, 1770, 2100), (660, 1260, 1860, 2220), (720, 1316, 1950, 2310), (750, 1372, 2040, 2430),
    )

    _NUM_ERROR_CORRECTION_BLOCKS = (
        (1, 1, 1, 1), (1, 1, 1, 1), (1, 1, 2, 2), (1, 2, 2, 4), (1, 2, 4, 4),
        (2, 4, 4, 4), (2, 4, 6, 5), (2, 4, 6, 6), (2, 5, 8, 8), (4, 5, 8, 8),
        (4, 5, 8, 11), (4, 8, 10, 11), (4, 9, 12, 16), (4, 9, 16, 16), (6, 10, 12, 18),
        (6, 10, 17, 16), (6, 11, 16, 19), (6, 13, 18, 21), (7, 14, 21, 25), (8, 16, 20, 25),
        (8, 17, 23, 25), (9, 17, 23, 34), (9, 18, 25, 30), (10, 20, 27, 32), (12, 21, 29, 35),
        (12, 23, 34, 37), (12, 25, 34, 40), (13, 26, 35, 42), (14, 28, 38, 45), (15, 29, 40, 48),
        (16, 31, 43, 51), (17, 33, 45, 54), (18, 35, 48, 57), (19, 37, 51, 60), (19, 38, 53, 63),
        (20, 40, 56, 66), (21, 43, 59, 70), (22, 45, 62, 74), (24, 47, 65, 77), (25, 49, 68, 81),
    )

    def __init__(self, version: int, ecc: EccLevel, data_codewords: Sequence[int], mask: int):
        if not (QrCode.MIN_VERSION <= version <= QrCode.MAX_VERSION):
            raise ValueError("Version number out of range")
        if not (0 <= mask <= 7):
            raise ValueError("Mask out of range")
        self.version = version
        self.error_correction_level = ecc
        self.mask = mask
        self.size = version * 4 + 17
        self.modules, self.is_function = _create_function_template(version)
        full_codewords = self._add_ecc_and_interleave(data_codewords)
        self._draw_codewords(full_codewords)
        self._apply_mask(mask)
        self._draw_format_bits(mask)

    @staticmethod
    def encode_text(text: str, ecc: EccLevel | None = None) -> "QrCode":
        if ecc is None:
            ecc = QrCode.LOW
        data = text.encode("utf-8")
        return QrCode.encode_binary(data, ecc)

    @staticmethod
    def encode_binary(data: bytes, ecc: EccLevel | None = None) -> "QrCode":
        if ecc is None:
            ecc = QrCode.LOW
        version = QrCode._choose_version(len(data), ecc)
        capacity_bits = QrCode._data_capacity_bits(version, ecc)
        char_count_bits = 8 if version <= 9 else 16
        bb = BitBuffer()
        bb.append_bits(0b0100, 4)
        bb.append_bits(len(data), char_count_bits)
        for b in data:
            bb.append_bits(b, 8)
        bb.append_terminator(capacity_bits)
        data_codewords = bb.to_codewords()
        data_codewords.extend(bb.pad_codewords(capacity_bits // 8 - len(data_codewords)))
        best = None
        best_penalty = None
        for mask in range(8):
            qr = QrCode(version, ecc, data_codewords, mask)
            penalty = qr._penalty_score()
            if best is None or penalty < best_penalty:  # type: ignore[operator]
                best = qr
                best_penalty = penalty
        assert best is not None
        return best

    @staticmethod
    def _choose_version(data_len: int, ecc: EccLevel) -> int:
        for version in range(QrCode.MIN_VERSION, QrCode.MAX_VERSION + 1):
            capacity_bits = QrCode._data_capacity_bits(version, ecc)
            char_count_bits = 8 if version <= 9 else 16
            total_bits = 4 + char_count_bits + data_len * 8
            if total_bits <= capacity_bits:
                return version
        raise ValueError("Data too long")

    @staticmethod
    def _data_capacity_bits(version: int, ecc: EccLevel) -> int:
        modules, is_function = _create_function_template(version)
        size = len(modules)
        data_modules = sum(1 for y in range(size) for x in range(size) if not is_function[y][x])
        total_codewords = data_modules // 8
        total_ecc = QrCode._ECC_CODEWORDS_PER_BLOCK[version - 1][ecc.ordinal]
        num_blocks = QrCode._NUM_ERROR_CORRECTION_BLOCKS[version - 1][ecc.ordinal]
        ecc_per_block = total_ecc // num_blocks
        data_codewords = total_codewords - total_ecc
        return data_codewords * 8

    def _draw_codewords(self, codewords: Sequence[int]) -> None:
        size = self.size
        i = 0
        upward = True
        for x in range(size - 1, -1, -2):
            if x == 6:
                x -= 1
            for y_offset in range(size):
                y = size - 1 - y_offset if upward else y_offset
                for dx in range(2):
                    xx = x - dx
                    if not self.is_function[y][xx] and i < len(codewords) * 8:
                        bit = (codewords[i // 8] >> (7 - i % 8)) & 1
                        self.modules[y][xx] = bool(bit)
                        i += 1
            upward = not upward

    def _apply_mask(self, mask: int) -> None:
        size = self.size
        for y in range(size):
            for x in range(size):
                if self.is_function[y][x]:
                    continue
                invert = False
                if mask == 0:
                    invert = (x + y) % 2 == 0
                elif mask == 1:
                    invert = y % 2 == 0
                elif mask == 2:
                    invert = x % 3 == 0
                elif mask == 3:
                    invert = (x + y) % 3 == 0
                elif mask == 4:
                    invert = (x // 3 + y // 2) % 2 == 0
                elif mask == 5:
                    invert = (x * y) % 2 + (x * y) % 3 == 0
                elif mask == 6:
                    invert = ((x * y) % 2 + (x * y) % 3) % 2 == 0
                elif mask == 7:
                    invert = ((x + y) % 2 + (x * y) % 3) % 2 == 0
                if invert:
                    self.modules[y][x] = not self.modules[y][x]

    def _draw_format_bits(self, mask: int) -> None:
        data = (self.error_correction_level.format_bits << 3) | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ (0x537 if (rem >> 9) & 1 else 0)
        bits = ((data << 10) | rem) ^ 0x5412
        for i in range(6):
            self.modules[i][8] = ((bits >> i) & 1) != 0
            self.modules[8][self.size - 1 - i] = ((bits >> i) & 1) != 0
        self.modules[7][8] = ((bits >> 6) & 1) != 0
        self.modules[8][self.size - 7] = ((bits >> 6) & 1) != 0
        self.modules[8][8] = ((bits >> 7) & 1) != 0
        self.modules[8][self.size - 8] = ((bits >> 7) & 1) != 0
        self.modules[8][7] = ((bits >> 8) & 1) != 0
        self.modules[self.size - 7][8] = ((bits >> 8) & 1) != 0
        for i in range(8):
            self.modules[self.size - 1 - i][8] = ((bits >> i) & 1) != 0
            if i < 7:
                self.modules[8][i] = ((bits >> (14 - i)) & 1) != 0

    def _penalty_score(self) -> int:
        size = self.size
        score = 0
        # Adjacent modules in row/column with same color
        for row in self.modules:
            score += _penalty_consecutive(row)
        for x in range(size):
            column = [self.modules[y][x] for y in range(size)]
            score += _penalty_consecutive(column)
        # 2x2 blocks
        for y in range(size - 1):
            for x in range(size - 1):
                if self.modules[y][x] == self.modules[y][x + 1] == self.modules[y + 1][x] == self.modules[y + 1][x + 1]:
                    score += 3
        # Finder-like patterns
        pattern1 = [True, False, True, True, True, False, True, False, False, False, False]
        pattern2 = [False, False, False, False, True, False, True, True, True, False, True]
        for row in self.modules:
            score += _penalty_pattern(row, pattern1, pattern2)
        for x in range(size):
            column = [self.modules[y][x] for y in range(size)]
            score += _penalty_pattern(column, pattern1, pattern2)
        # Dark module ratio
        dark = sum(row.count(True) for row in self.modules)
        total = size * size
        k = abs(dark * 20 - total * 10) // total
        score += k * 10
        return score

    def get_matrix(self) -> List[List[bool]]:
        return [row[:] for row in self.modules]

    def _add_ecc_and_interleave(self, data: Sequence[int]) -> List[int]:
        version = self.version
        total_ecc = QrCode._ECC_CODEWORDS_PER_BLOCK[version - 1][self.error_correction_level.ordinal]
        num_blocks = QrCode._NUM_ERROR_CORRECTION_BLOCKS[version - 1][self.error_correction_level.ordinal]
        ecc_len = total_ecc // num_blocks
        total_codewords = len(data) + total_ecc
        short_block_len = len(data) // num_blocks
        num_long_blocks = len(data) % num_blocks
        blocks = []
        k = 0
        rs = ReedSolomonGenerator(ecc_len)
        for i in range(num_blocks):
            block_len = short_block_len + (1 if i < num_long_blocks else 0)
            block_data = list(data[k:k + block_len])
            k += block_len
            ecc = rs.remainder(block_data)
            blocks.append((block_data, ecc))
        result = []
        max_len = short_block_len + 1
        for i in range(max_len):
            for block in blocks:
                if i < len(block[0]):
                    result.append(block[0][i])
        for i in range(ecc_len):
            for block in blocks:
                result.append(block[1][i])
        assert len(result) == total_codewords
        return result


class BitBuffer:
    def __init__(self) -> None:
        self.bits: List[int] = []

    def append_bits(self, value: int, length: int) -> None:
        for i in reversed(range(length)):
            self.bits.append((value >> i) & 1)

    def append_terminator(self, capacity_bits: int) -> None:
        terminator = min(4, capacity_bits - len(self.bits))
        self.bits.extend([0] * terminator)
        extra = (8 - len(self.bits) % 8) % 8
        self.bits.extend([0] * extra)

    def to_codewords(self) -> List[int]:
        codewords = []
        for i in range(0, len(self.bits), 8):
            chunk = 0
            for bit in self.bits[i:i + 8]:
                chunk = (chunk << 1) | bit
            codewords.append(chunk)
        return codewords

    def pad_codewords(self, count: int) -> List[int]:
        pads = [0xEC, 0x11]
        return [pads[i % 2] for i in range(count)]


class ReedSolomonGenerator:
    def __init__(self, degree: int):
        if degree <= 0 or degree > 255:
            raise ValueError("Degree out of range")
        self.coefficients = [1]
        root = 1
        for _ in range(degree):
            self.coefficients = self._multiply(self.coefficients, [1, root])
            root = self._gf_multiply(root, 0x02)

    @staticmethod
    def _multiply(p: Sequence[int], q: Sequence[int]) -> List[int]:
        result = [0] * (len(p) + len(q) - 1)
        for i, a in enumerate(p):
            for j, b in enumerate(q):
                result[i + j] ^= ReedSolomonGenerator._gf_multiply(a, b)
        return result

    @staticmethod
    def _gf_multiply(x: int, y: int) -> int:
        z = 0
        for _ in range(8):
            if y & 1:
                z ^= x
            carry = x & 0x80
            x = (x << 1) & 0xFF
            if carry:
                x ^= 0x1D
            y >>= 1
        return z

    def remainder(self, data: Sequence[int]) -> List[int]:
        result = [0] * (len(self.coefficients) - 1)
        for byte in data:
            factor = byte ^ result[0]
            result = result[1:] + [0]
            for i in range(len(result)):
                result[i] ^= self._gf_multiply(self.coefficients[i + 1], factor)
        return result


def _create_function_template(version: int) -> tuple[List[List[bool]], List[List[bool]]]:
    size = version * 4 + 17
    modules = [[False] * size for _ in range(size)]
    is_function = [[False] * size for _ in range(size)]

    finder = [
        [True, True, True, True, True, True, True],
        [True, False, False, False, False, False, True],
        [True, False, True, True, True, False, True],
        [True, False, True, True, True, False, True],
        [True, False, True, True, True, False, True],
        [True, False, False, False, False, False, True],
        [True, True, True, True, True, True, True],
    ]

    def place_finder(cx: int, cy: int) -> None:
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                x = cx + dx
                y = cy + dy
                if 0 <= x < size and 0 <= y < size:
                    modules[y][x] = finder[dy + 3][dx + 3]
                    is_function[y][x] = True
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x = cx + dx
                y = cy + dy
                if 0 <= x < size and 0 <= y < size:
                    if abs(dx) == 4 or abs(dy) == 4:
                        modules[y][x] = False
                        is_function[y][x] = True

    place_finder(3, 3)
    place_finder(size - 4, 3)
    place_finder(3, size - 4)

    for i in range(8, size - 8):
        modules[6][i] = i % 2 == 0
        modules[i][6] = i % 2 == 0
        is_function[6][i] = True
        is_function[i][6] = True

    modules[size - 8][8] = True
    is_function[size - 8][8] = True

    positions = _alignment_pattern_positions(version)
    for r in positions:
        for c in positions:
            if (r == 6 and c == 6) or (r == 6 and c == size - 7) or (r == size - 7 and c == 6):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    x = c + dx
                    y = r + dy
                    modules[y][x] = max(abs(dx), abs(dy)) != 1
                    is_function[y][x] = True

    for i in range(0, 9):
        if i == 6:
            continue
        is_function[8][i] = True
        is_function[i][8] = True
    for i in range(size - 8, size):
        is_function[8][i] = True
        is_function[size - 1 - (i - (size - 8))][8] = True
    is_function[8][8] = True
    is_function[7][8] = True
    is_function[8][7] = True

    if version >= 7:
        bits = version
        for i in range(18):
            bit = (bits >> i) & 1
            x = size - 11 + (i % 3)
            y = i // 3
            modules[y][x] = bool(bit)
            modules[size - 1 - y][i % 3] = bool(bit)
            is_function[y][x] = True
            is_function[size - 1 - y][i % 3] = True

    return modules, is_function


def _alignment_pattern_positions(version: int) -> List[int]:
    if version == 1:
        return []
    num = version // 7 + 2
    step = 26 if version == 32 else ((version * 4 + num * 2 + 1) // (2 * num - 2)) * 2
    result = [6]
    for _ in range(num - 2):
        result.append(result[-1] + step)
    result.append(version * 4 + 10)
    return result


def _penalty_consecutive(line: Sequence[bool]) -> int:
    score = 0
    run_color = False
    run_length = 0
    for color in line:
        if color == run_color:
            run_length += 1
            if run_length == 5:
                score += 3
            elif run_length > 5:
                score += 1
        else:
            run_color = color
            run_length = 1
    return score


def _penalty_pattern(line: Sequence[bool], p1: Sequence[bool], p2: Sequence[bool]) -> int:
    score = 0
    for i in range(len(line) - len(p1) + 1):
        if list(line[i:i + len(p1)]) == list(p1) or list(line[i:i + len(p2)]) == list(p2):
            score += 40
    return score
