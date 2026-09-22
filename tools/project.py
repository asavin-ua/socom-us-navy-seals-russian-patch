"""SOCOM v3.00 workspace: resource audit and direct ISO build."""
from pathlib import Path
import argparse, hashlib, json, os, struct
from socom_formats import records, sections, u32, allrefs
from rdr_runtime import runtime_roundtrip
from animation_runtime import inspect

ROOT=Path(__file__).resolve().parents[1]
CHUNK=8*1024*1024
def local(p):
    result=(ROOT/p).resolve();assert result.is_relative_to(ROOT.resolve());return result
def supplied(p):return Path(p).expanduser().resolve()
def cfg():return json.loads((ROOT/'project.json').read_text(encoding='utf8'))
def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=True,indent=2)+'\n',encoding='utf8')
def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def directories(path):
    result={}
    with path.open('rb') as f:
        f.seek(16*2048);pvd=f.read(2048);assert pvd[:7]==b'\1CD001\1';root=pvd[156:190]
        def walk(lba,size,parent):
            f.seek(lba*2048);data=f.read(size);i=0
            while i<len(data):
                n=data[i]
                if not n:i=(i//2048+1)*2048;continue
                r=data[i:i+n];position=lba*2048+i;i+=n;name=r[33:33+r[32]]
                if name in (b'\0',b'\1'):continue
                p=parent+'/'+name.decode('ascii').split(';')[0]
                result[p]=dict(offset=position,lba=u32(r,2),size=u32(r,10),dir=bool(r[25]&2))
                if r[25]&2:walk(u32(r,2),u32(r,10),p)
        walk(u32(root,2),u32(root,10),'')
        f.seek(17*2048);assert f.read(7)==b'\xffCD001\1'
    return result
def audit(report=None):
    c=cfg();files=local(c['resources']);manifest=json.loads(local(c['manifest']).read_text())
    inv={r['path']:r for r in json.loads(local(c['inventory']).read_text()) if not r['dir']}
    assert {'/'+f.relative_to(files).as_posix() for f in files.rglob('*') if f.is_file()}=={r['path'] for r in manifest}
    rows=[];tables=0
    for r in manifest:
        p=r['path'];f=local(c['resources']+'/'+p.lstrip('/'));b=f.read_bytes()
        assert p in inv and len(b)==r['size'] and hashlib.sha256(b).hexdigest()==r['sha256'],p
        assert not any(x in p for x in ['/MOVIES/','VAGSTORE','BNKSTORE','/RECO/'])
        row=dict(path=p,sha256=r['sha256']);checks=[]
        if p.endswith(('.ZAR','.ZED')):
            rr,_,base=records(b);assert u32(b,84)==len(b)-base
            assert all(base<=x['offset']<=x['offset']+x['size']<=len(b) for x in rr)
        if 'ZANIM' in p:
            result=inspect(b,True);tables+=result['table_count'];row['animation']=result
        if f.name.startswith('READER'):
            for n,s,z in sections(b):
                external=[x for x in allrefs(b,s,z) if x['end'] is None]
                if external:
                    assert n=='zweapon.rdr'
                    checks.append(dict(section=n,external_string_sentinels_preserved=len(external)))
                else:checks.append(dict(section=n,**runtime_roundtrip(b,s,z)))
            row['readers']=checks
        rows.append(row)
    result=dict(status='passed',files=rows,resources=len(rows),animation_tables=tables)
    if report:dump(supplied(report),result)
    print(f'Resources verified: {len(rows)}; animation tables: {tables}',flush=True)
    return manifest,inv
def verify_iso(path,manifest,inv):
    positions=directories(path);expected={p:r['sha256'] for p,r in inv.items()}
    expected.update({r['path']:r['sha256'] for r in manifest})
    assert {p for p,r in positions.items() if not r['dir']}==set(expected)
    with path.open('rb') as f:
        for p,sha in expected.items():
            r=positions[p];f.seek(r['lba']*2048);h=hashlib.sha256();left=r['size']
            while left:
                b=f.read(min(left,8*1024*1024));assert b;h.update(b);left-=len(b)
            assert h.hexdigest()==sha,p
    audio=[p for p in expected if any(x in p for x in ['/MOVIES/','VAGSTORE','BNKSTORE','/RECO/'])]
    assert all(expected[p]==inv[p]['sha256'] for p in audio)
    return dict(all_files_verified=len(expected),original_audio_files_preserved=len(audio),sha256=digest(path))
def plan(source,manifest):
    """Plan direct resource replacement in a clean English ISO."""
    c=cfg();base=supplied(source)
    assert digest(base)==c['original']['sha256'] and base.stat().st_size==c['original']['size']
    pos=directories(base)
    ops=[];tail=bytearray();length=base.stat().st_size
    with base.open('rb') as f:
        def op(offset,new):
            f.seek(offset);old=f.read(len(new));assert len(old)==len(new)
            if old!=new:ops.append((offset,old,bytes(new)))
        for row in manifest:
            p=row['path'];r=pos[p];new=local(c['resources']+'/'+p.lstrip('/')).read_bytes()
            if len(new)<=((r['size']+2047)//2048)*2048:lba=r['lba'];op(lba*2048,new)
            else:lba=(length+len(tail))//2048;tail+=new;tail+=bytes((-len(tail))%2048)
            f.seek(r['offset']);entry=bytearray(f.read(34))
            struct.pack_into('<I',entry,2,lba);struct.pack_into('>I',entry,6,lba)
            struct.pack_into('<I',entry,10,len(new));struct.pack_into('>I',entry,14,len(new));op(r['offset'],entry)
        sectors=(length+len(tail))//2048;op(16*2048+80,struct.pack('<I',sectors)+struct.pack('>I',sectors))
    ops.sort(key=lambda x:x[0])
    for x,y in zip(ops,ops[1:]):assert x[0]+len(x[1])<=y[0]
    ops.append((length,b'',bytes(tail)))
    return ops,length+len(tail)
def apply_plan(source,ops,output_size,output=None):
    c=cfg();source=supplied(source);target=supplied(output) if output else None
    if target:
        assert target!=source and not target.exists(),'Output already exists; choose a new path'
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_name(target.name+'.partial');out=temporary.open('xb')
    else:temporary=None;out=None
    h=hashlib.sha256();size=0;cursor=0
    def emit(data):
        nonlocal size
        h.update(data);size+=len(data)
        if out:out.write(data)
    try:
        with source.open('rb') as f:
            for offset,old,new in ops:
                while cursor<offset:
                    data=f.read(min(CHUNK,offset-cursor));assert data
                    emit(data);cursor+=len(data)
                assert f.read(len(old))==old,('Source bytes mismatch',offset)
                cursor+=len(old);emit(new)
            while data:=f.read(CHUNK):emit(data)
        assert size==output_size==c['current']['size']
        assert h.hexdigest()==c['current']['sha256'],'Output verification failed'
    finally:
        if out:out.close()
    if target:
        assert digest(temporary)==c['current']['sha256'],'Written ISO verification failed'
        assert not target.exists();os.rename(temporary,target)
    return dict(status='passed',source_sha256=c['original']['sha256'],output_sha256=h.hexdigest(),
        size=size,output=str(target) if target else None,mode='build' if target else 'verify')
def build_image(source,output=None):
    target=supplied(output) if output else None
    if target:assert not target.exists(),'Output already exists; choose a new path'
    manifest,inv=audit();ops,output_size=plan(source,manifest)
    result=apply_plan(source,ops,output_size,target)
    if target:result.update(verify_iso(target,manifest,inv),all_resources_verified=True)
    return result
def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='command',required=True)
    s.add_parser('status')
    q=s.add_parser('audit');q.add_argument('--report')
    q=s.add_parser('build');q.add_argument('--input',required=True);q.add_argument('--output',required=True)
    q=s.add_parser('verify');q.add_argument('--input',required=True);q.add_argument('--translated')
    a=p.parse_args();c=cfg()
    if a.command=='status':
        print(json.dumps(c,ensure_ascii=True,indent=2));return
    if a.command=='audit':audit(a.report);return
    if a.command=='build':
        result=build_image(a.input,a.output)
    else:
        result=build_image(a.input)
        if a.translated:
            manifest,inv=audit();path=supplied(a.translated);assert digest(path)==c['current']['sha256']
            result.update(verify_iso(path,manifest,inv));result['path']=str(path)
    print(json.dumps(result),flush=True)
if __name__=='__main__':main()
