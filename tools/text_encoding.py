"""Verified game-byte encodings; use only for display strings, never resource IDs."""
GLYPHS = dict(zip('АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЫЬЭЮЯ',
    [0x41,0xc1,0x42,0xcb,0xc2,0x45,0xc4,0x33,0xc8,0x4b,0xc9,0x4d,0x48,0x4f,0xca,0x50,0x43,0x54,0xdc,0xd6,0x58,0xc7,0x34,0xd2,0xd3,0xc0,0xd9,0xda,0xd4,0xdb]))
GLYPHS.update({'Й':0xcf, 'Ё':0xcd, 'Ъ':0xce})
ORDER_ALIASES={'И':'#','Й':'^','Ё':'~','Л':'$','У':'&','Я':'%','Ф':'@','Щ':';','Ь':'6','Ъ':'|'}
SPECIAL={'Й':0xdd,'Ё':0xde,'Ъ':0xdf}
def encode(text):
    out=bytearray()
    for ch in text.upper():
        if ch in GLYPHS:out.append(GLYPHS[ch])
        else:
            assert ord(ch)<128,('Unsupported character',ch)
            out.append(ord(ch))
    return bytes(out)
def encode_orders(text):
    return b''.join(ORDER_ALIASES[c].encode('ascii') if c in ORDER_ALIASES else encode(c) for c in text.upper())
def encode_loading(text):
    return b''.join(bytes([SPECIAL[c]]) if c in SPECIAL else encode(c) for c in text.upper())
def game_string(text,face='ui'):
    return {'ui':encode,'orders':encode_orders,'loading':encode_loading}[face](text).decode('latin1')
