"""Apply and audit the visible objective popups in single-player animations."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from animation_runtime import inspect
from socom_formats import change_names, decode, records
from text_encoding import encode

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'sources/dictionaries/objective_completion_popups.json'
UNTRANSLATED = re.compile(r'[A-Z][A-Z ]+[A-Z]')


def name_entries(data):
    entries, _, _ = records(data)
    tables = [item for item in entries if item['name'] == 'Name_Table' and item['children']]
    assert len(tables) == 1 and entries[tables[0]['index'] - 2]['name'] == 'mission'
    table = tables[0]
    return entries[table['index'] + 1:table['index'] + 1 + table['children']]


def resource_path(mission):
    assert re.fullmatch(r'M\d+', mission)
    return ROOT / 'resources/files/RUN/SP' / mission / 'MZANIM.ZAR'


def translated(row):
    return encode(row['russian']).decode('latin1')


def load_spec():
    spec = json.loads(SPEC.read_text(encoding='utf-8'))
    assert spec['encoding'] == 'ui'
    assert spec['missions'] and all(spec['missions'].values())
    for mission, rows in spec['missions'].items():
        assert len({row['index'] for row in rows}) == len(rows), mission
        assert len({translated(row) for row in rows}) == len(rows), mission
    font_data = (ROOT / 'resources/files/RUN/UI/READERC.ZAR').read_bytes()
    font_records, _, _ = records(font_data)
    font_section = next(item for item in font_records if item['name'] == 'fonts.rdr')
    tree = decode(font_data, font_section['offset'], font_section['size'])
    raw_faces = tree[0][1]
    faces = dict(zip(raw_faces[::2], raw_faces[1::2]))
    used = {byte for rows in spec['missions'].values() for row in rows
            for byte in encode(row['russian'])}
    for face_name in ('Gothic_13', 'arialblack', 'myriad'):
        face = faces[face_name]
        offsets = dict(zip(face[::2], face[1::2]))['charoffsets']
        covered = {ord(item[0]) for item in offsets
                   if isinstance(item[0], str) and len(item[0]) == 1}
        assert used <= covered, (face_name, sorted(used - covered))
    return spec['missions']


def apply():
    missions = load_spec()
    manifest_path = ROOT / 'resources/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    by_path = {row['path']: row for row in manifest}
    planned = {}
    for mission, rows in missions.items():
        path = resource_path(mission)
        data = path.read_bytes()
        names = name_entries(data)
        changes = {}
        for row in rows:
            index = row['index']
            assert 0 <= index < len(names), (mission, index)
            old_values = {row['english']}
            if 'previous' in row:
                old_values.add(encode(row['previous']).decode('latin1'))
            if names[index]['name'] == translated(row):
                continue
            if names[index]['name'] in old_values:
                changes[names[index]['index']] = translated(row)
            else:
                raise AssertionError((mission, index, names[index]['name']))
        result = change_names(data, changes) if changes else data
        inspect(result, True)
        planned[mission] = result
    for mission, data in planned.items():
        path = resource_path(mission)
        path.write_bytes(data)
        entry = by_path['/RUN/SP/' + mission + '/MZANIM.ZAR']
        entry['sha256'] = hashlib.sha256(data).hexdigest()
        entry['size'] = len(data)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    verify()
    print('Applied objective popup translations:', sum(map(len, missions.values())))


def verify():
    missions = load_spec()
    checked = 0
    paths = sorted((ROOT / 'resources/files/RUN/SP').glob('M*/MZANIM.ZAR'))
    assert len(paths) == 12
    for path in paths:
        data = path.read_bytes()
        names = name_entries(data)
        for row in missions.get(path.parent.name, []):
            assert names[row['index']]['name'] == translated(row), (path, row['index'])
            checked += 1
        leftover = [(i, item['name']) for i, item in enumerate(names)
                    if ' ' in item['name'] and UNTRANSLATED.fullmatch(item['name'])]
        assert not leftover, (path, leftover)
    assert checked == sum(map(len, missions.values()))
    return checked


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply:
        apply()
    else:
        print('Objective popup titles verified:', verify())
