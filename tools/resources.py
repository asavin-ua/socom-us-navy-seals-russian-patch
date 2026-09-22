"""Export editable RDR trees and apply reviewed edits on the current Git branch."""
from pathlib import Path
import argparse, hashlib, json
from project import ROOT, cfg, local, dump
from socom_formats import sections, records, decode, serialize_fit, repack_sections, allrefs
from rdr_runtime import runtime_roundtrip

def sha(b):return hashlib.sha256(b).hexdigest()
def export():
    c=cfg();root=local(c['resources']);index=[]
    for f in sorted(root.rglob('*')):
        if not f.is_file():continue
        path='/'+f.relative_to(root).as_posix();b=f.read_bytes()
        if f.name.startswith('READER'):
            for name,s,z in sections(b):
                raw=b[s:s+z];external=any(r['end'] is None for r in allrefs(b,s,z))
                record=dict(resource=path,resource_sha256=sha(b),section=name,section_sha256=sha(raw))
                target=ROOT/'sources/rdr'/path.lstrip('/')/(name+'.json')
                if external:
                    target=target.with_suffix('.bin');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                    record['external_string_sentinels']=True
                else:
                    tree=decode(raw,0,len(raw));record['tree']=tree;dump(target,record)
                index.append(dict(resource=path,section=name,file=target.relative_to(ROOT).as_posix(),editable_json=not external))
        elif 'ZANIM' in f.name or f.name=='ZWEAPON.ZAR':
            rr,_,_=records(b)
            dump(ROOT/'sources/compiled'/path.lstrip('/')/'names.json',dict(resource=path,sha256=sha(b),
                note='Reference only: includes protected internal names. Do not mass-translate.',
                records=[{k:r[k] for k in ['index','name','children','size']} for r in rr]))
    dump(ROOT/'sources/index.json',index)
    print('Exported',len(index),'RDR sections and compiled-name catalogs.')
def apply_edit(source):
    source_path=local(source);doc=json.loads(source_path.read_text(encoding='utf8'));c=cfg()
    resource=local(c['resources']+'/'+doc['resource'].lstrip('/'));before=resource.read_bytes()
    assert sha(before)==doc['resource_sha256'],'Edit was based on another resource revision'
    _,s,z=next(r for r in sections(before) if r[0]==doc['section'])
    old=before[s:s+z];assert sha(old)==doc['section_sha256']
    if decode(old,0,len(old))==doc['tree']:
        print('No changes; original bytes retained.');return
    raw=serialize_fit(doc['tree'],len(old));check=runtime_roundtrip(raw,0,len(raw))
    after=repack_sections(before,{doc['section']:raw})
    manifest_path=local(c['manifest']);manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    row=next(r for r in manifest if r['path']==doc['resource'])
    assert row['sha256']==sha(before) and row['size']==len(before),'Manifest does not describe the current resource'
    row.update(sha256=sha(after),size=len(after))
    _,new_start,new_size=next(r for r in sections(after) if r[0]==doc['section'])
    doc.update(resource_sha256=sha(after),section_sha256=sha(after[new_start:new_start+new_size]))
    resource.write_bytes(after);dump(manifest_path,manifest);dump(source_path,doc)
    print('Applied on current Git branch:',resource,'; runtime:',json.dumps(check,separators=(',',':')))
if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('export');s=sub.add_parser('apply');s.add_argument('--input',required=True)
    a=p.parse_args()
    if a.command=='export':export()
    else:apply_edit(a.input)
