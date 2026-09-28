"""Check the Cyrillic glyph links and ink in the shipped font resources."""
from collections import Counter
from pathlib import Path

from socom_formats import decode, records
from text_encoding import encode, encode_loading, encode_orders

EXPECTED = {
    'Gothic_13': {
        0x3b: ((291, 69), (312, 111)),
        0x5e: ((0, 128), (19, 169)),
        0x7c: ((49, 128), (74, 170)),
        0x7e: ((24, 128), (44, 170)),
        0xcd: ((24, 128), (44, 170)),
        0xce: ((49, 128), (74, 170)),
        0xcf: ((0, 128), (19, 169)),
        0xd1: ((228, 70), (249, 110)),
        0xd3: ((291, 69), (312, 111)),
    },
    'arialblack': {
        0x3b: ((297, 98), (313, 124)),
        0x5e: ((195, 98), (207, 123)),
        0x60: ((224, 22), (230, 27)),
        0x7c: ((466, 40), (486, 66)),
        0x7e: ((211, 98), (223, 123)),
        0xcd: ((211, 98), (223, 123)),
        0xce: ((466, 40), (486, 66)),
        0xcf: ((195, 98), (207, 123)),
        0xd1: ((488, 98), (501, 123)),
        0xd3: ((297, 98), (313, 124)),
    },
    'myriad': {
        0x3b: ((226, 224), (251, 255)),
        0x5e: ((286, 189), (305, 222)),
        0x60: ((174, 92), (184, 100)),
        0x7c: ((80, 223), (110, 255)),
        0x7e: ((307, 189), (326, 222)),
        0xcd: ((307, 189), (326, 222)),
        0xce: ((80, 223), (110, 255)),
        0xcf: ((286, 189), (305, 222)),
        0xd1: ((56, 224), (78, 255)),
        0xd3: ((226, 224), (251, 255)),
    },
    'myriad_load': {
        0xdd: ((98, 38), (111, 56)),
        0xde: ((174, 38), (185, 56)),
    },
}
FONT_FILES = ('RUN/READERC.ZAR', 'RUN/UI/READERC.ZAR', 'RUN/UI/READERX.ZAR')


def texture(root, relative, name):
    data = (root / 'resources/files' / relative).read_bytes()
    entries, _, _ = records(data)
    index = next(i for i, entry in enumerate(entries) if entry['name'] == name)
    record = entries[index + 1]
    assert record['name'] == 'texdat'
    return data[record['offset'] + 160:record['offset'] + record['size']]


def glyph_pixels(pixels, width, height, shift, rect, depth=1):
    (left, top), (right, bottom) = rect
    assert 0 <= left < right < width and 0 <= top < bottom <= height
    return [
        pixels[(((height - 1 - y) * width + (x - shift) % width) * depth):
               (((height - 1 - y) * width + (x - shift) % width) * depth + depth)]
        for y in range(top, bottom + 1) for x in range(left, right + 1)
    ]


def verify(root):
    """Raise AssertionError if a link or its texture ink regresses."""
    root = Path(root)
    assert encode('ЙЁЪЩ') == bytes((0xcf, 0xcd, 0xce, 0xd3))
    assert encode_orders('ЙЁЪЩ') == bytes((0x5e, 0x7e, 0x7c, 0x3b))
    assert encode_orders('ПОМОЩЬ') == bytes((0xca, 0x4f, 0x4d, 0x4f, 0x3b, 0x36))
    assert encode_loading('ЙЁ') == bytes((0xdd, 0xde))
    orders_data = (root / 'resources/files/RUN/READERC.ZAR').read_bytes()
    orders_entry = next(item for item in records(orders_data)[0] if item['name'] == 'orders.rdr')
    orders_tree = decode(orders_data, orders_entry['offset'], orders_entry['size'])
    orders = dict(zip(orders_tree[0][::2], orders_tree[0][1::2]))
    assert orders['teamtable'][3][0].encode('latin1') == encode_orders('ПОМОЩЬ')
    assert orders['teamtable'][1][0].encode('latin1') == encode_orders('ЭЙБЛ')
    order_strings = []
    def collect(node):
        if isinstance(node, str):
            order_strings.append(node)
        elif isinstance(node, list):
            for child in node:
                collect(child)
    collect(orders_tree)
    for translated in ('ЭЙБЛ', 'СЛЕДУЙ', 'ПРИКРОЙ', 'БАНЗАЙ', 'СТРЕЛЯЙ', 'УМИРАЙ', 'ТВОЕЙ', 'НОВЫЙ', 'ТВОЙ'):
        assert any(encode_orders(translated).decode('latin1') in string for string in order_strings), translated
    for unconverted in ('TBO#', 'TBOE#', 'CTPE$%#', '&M#PA#', 'HOB\xc0#', '\xc1AH3A#', '\xcaP#KPO#'):
        assert not any(unconverted in string for string in order_strings), unconverted
    font_faces = {}
    for relative in FONT_FILES:
        data = (root / 'resources/files' / relative).read_bytes()
        entries, _, _ = records(data)
        entry = next(item for item in entries if item['name'] == 'fonts.rdr')
        tree = decode(data, entry['offset'], entry['size'])
        raw_faces = tree[0][1]
        faces = dict(zip(raw_faces[::2], raw_faces[1::2]))
        font_faces[relative] = {}
        for name, expected in EXPECTED.items():
            face = faces[name]
            values = dict(zip(face[::2], face[1::2]))['charoffsets']
            offsets = {}
            for item in values:
                if not isinstance(item[0], str) or len(item[0]) != 1:
                    continue
                offsets.setdefault(ord(item[0]), []).append((tuple(item[1]), tuple(item[2])))
            for code, rect in expected.items():
                assert offsets.get(code) and all(hit == rect for hit in offsets[code]), (relative, name, hex(code))
            if name == 'Gothic_13':
                assert 0x60 not in offsets, relative
            font_faces[relative][name] = offsets

    ui = 'RUN/UI/ASSETLIB/UI2D/UI2D_TXR.ZED'
    mp = 'RUN/UI/ASSETLIB/UIMP/UIMP_TXR.ZED'
    common = 'RUN/COMMON/ASSETLIB/FONT/FONT_TXR.ZED'
    base = font_faces['RUN/UI/READERC.ZAR']
    for face, relative, name, height, fill in (
        ('Gothic_13', ui, 'Gothic_13.tif', 256, 122),
        ('myriad', ui, 'myriad_font.tif', 256, 105),
        ('arialblack', common, 'arialblack.tif', 128, 116),
    ):
        pixels = texture(root, relative, name)
        assert len(pixels) == 512 * height
        glyphs = base[face]
        def ink(code):
            return [part[0] for part in glyph_pixels(pixels, 512, height, 128, glyphs[code][-1])]
        assert set(ink(0xcf)) - {0} <= set(ink(0xc8)) - {0}, face
        assert set(ink(0xcd)) - {0} <= set(ink(ord('E'))) - {0}, face
        for code in (0x3b, 0x5e, 0x7c, 0x7e, 0xcd, 0xce, 0xcf, 0xd3):
            counts = Counter(ink(code))
            counts.pop(0, None)
            assert counts and counts.most_common(1)[0][0] == fill, (face, hex(code))
        if relative == ui:
            other = texture(root, mp, name)
            for code in (0x3b, 0x5e, 0x7c, 0x7e, 0xcd, 0xce, 0xcf, 0xd3):
                rect = glyphs[code][-1]
                assert glyph_pixels(pixels, 512, height, 128, rect) == glyph_pixels(other, 512, height, 128, rect)

    loading = texture(root, 'RUN/COMMON/ASSETLIB/LOADING/LOAD_TXR.ZED', 'myriad_load.tif')
    assert len(loading) == 256 * 64 * 4
    for code in (0xdd, 0xde):
        parts = glyph_pixels(loading, 256, 64, 32, base['myriad_load'][code][-1], depth=4)
        assert any(part[3] for part in parts)
        assert all(part[:3] == bytes((255, 255, 255)) for part in parts), hex(code)


if __name__ == '__main__':
    verify(Path(__file__).resolve().parents[1])
    print('Font glyph links and ink verified')
