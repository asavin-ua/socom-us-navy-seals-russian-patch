"""SOCOM v3 format helpers, extracted from the established safe implementations."""
import copy, struct
from rdr_runtime import runtime_roundtrip

def u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]

def sections(data):
    count = u32(data, 4) - 1
    table = 100 + u32(data, 8) + 16
    base = (table + count * 16 + 15) & ~15
    result = []
    for i in range(count):
        ptr, relative, size, _ = struct.unpack_from('<4I', data, table + i * 16)
        namepos = 100 + ptr - u32(data, 12)
        name = data[namepos:data.index(0, namepos)].decode('ascii')
        start = base + relative
        assert start + size <= len(data)
        result.append((name, start, size))
    return result

def records(data):
    count = u32(data, 4)-1
    table = 100+u32(data, 8)+16
    base = (table+count*16+15)&~15
    out = []
    for i in range(count):
        ptr, off, size, children = struct.unpack_from('<4I', data, table+i*16)
        pos = 100+ptr-u32(data, 12)
        assert 100 <= pos < 100+u32(data, 8)
        end = data.index(0, pos, 100+u32(data, 8))
        assert base+off+size <= len(data)
        out.append({'index': i, 'name': data[pos:end].decode('latin1'),
                    'name_offset': pos, 'offset': base+off, 'size': size,
                    'children': children})
    return out, table, base

def decode(data,start,size):
    pool=start+8;tree=start+u32(data,start+4);seen={}
    def walk(pos,anc):
        assert pos not in anc and tree<=pos<start+size and u32(data,pos)==1
        if pos in seen:return copy.deepcopy(seen[pos])
        out=[];count=u32(data,pos+4);assert pos+count*8<=start+size
        for i in range(1,count):
            kind,val=struct.unpack_from('<II',data,pos+i*8)
            if kind==1:out.append(val)
            elif kind==2:out.append(struct.unpack('<f',struct.pack('<I',val))[0])
            elif kind==3:
                off=pool+val;assert pool<=off<pool+u32(data,start)
                out.append(data[off:data.index(0,off,pool+u32(data,start))].decode('latin1'))
            else:
                assert kind==4
                out.append(walk(tree+val,anc|{pos}))
        seen[pos]=out;return copy.deepcopy(out)
    return walk(tree,set())

def serialize(obj,capacity):
    """Share only numeric leaves: the game relocates pointer entries in place."""
    pool=bytearray();strings={};tree=bytearray();nodes={}
    def freeze(v):
        if isinstance(v,list):return (4,tuple(map(freeze,v)))
        if isinstance(v,str):return (3,v)
        if isinstance(v,float):return (2,struct.pack('<f',v))
        return (1,v)
    def node(v):
        key=freeze(v)
        shareable=all(isinstance(x,(int,float)) for x in v)
        if shareable and key in nodes:return nodes[key]
        off=len(tree)
        if shareable:nodes[key]=off
        tree.extend(bytes((len(v)+1)*8))
        struct.pack_into('<II',tree,off,1,len(v)+1)
        for i,x in enumerate(v,1):
            if isinstance(x,list):kind,value=4,node(x)
            elif isinstance(x,str):
                if x not in strings:strings[x]=len(pool);pool.extend(x.encode('latin1')+b'\0')
                kind,value=3,strings[x]
            elif isinstance(x,float):kind,value=2,struct.unpack('<I',struct.pack('<f',x))[0]
            else:kind,value=1,x
            struct.pack_into('<II',tree,off+i*8,kind,value)
        return off
    assert node(obj)==0
    tree_start=(8+len(pool)+3)&~3
    result=struct.pack('<II',len(pool),tree_start)+pool+bytes(tree_start-8-len(pool))+tree
    assert len(result)<=capacity,('Section capacity',len(result),capacity)
    result+=bytes(capacity-len(result))
    assert decode(result,0,capacity)==obj
    runtime_roundtrip(result,0,capacity)
    return result

def value(obj,key):return obj[obj.index(key)+1]

def setvalue(obj,key,v):obj[obj.index(key)+1]=v

def allrefs(data,start,size):
    """Preserve the legacy weapon reader's external string sentinels verbatim."""
    pool=start+8;end=pool+u32(data,start);tree=start+u32(data,start+4);out=[]
    def walk(pos,path,anc):
        assert pos not in anc and tree<=pos<start+size and u32(data,pos)==1
        count=u32(data,pos+4);assert pos+count*8<=start+size
        label=None
        for i in range(1,count):
            word=pos+i*8;kind,v=struct.unpack_from('<II',data,word)
            if kind==3:
                off=pool+v
                text='<external-string>';stop=None
                if pool<=off<end:stop=data.index(0,off,end);text=data[off:stop].decode('latin1')
                out.append(dict(word=word+4,offset=off,end=stop,text=text,context=path));label=text
            elif kind==4:walk(tree+v,path+'/'+(label or str(i-1)),anc|{pos});label=None
    walk(tree,'',set());return out

def serialize_fit(obj,capacity):
    try:return serialize(obj,capacity)
    except AssertionError as ex:
        if not ex.args or not isinstance(ex.args[0],tuple) or ex.args[0][0]!='Section capacity':raise
        return serialize(obj,(ex.args[0][1]+15)&~15)

def repack_sections(data,changed):
    rr,table,base=records(data);out=bytearray(data[:base]);oldsections=sections(data)
    assert len(rr)==len(oldsections)
    for r,(name,s,z) in zip(rr,oldsections):
        payload=changed.get(name,data[s:s+z]);out+=bytes((-len(out))%16);start=len(out);out+=payload
        struct.pack_into('<II',out,table+r['index']*16+4,start-base,len(payload))
    out+=bytes((-len(out))%16)
    struct.pack_into('<I',out,84,len(out)-base)
    assert len(sections(out))==len(oldsections)
    return bytes(out)

def change_names(data,changes):
    """Append strings; keep all data offsets relative to the new payload base."""
    rr,table,base=records(data);pool=bytearray(data[100:100+u32(data,8)]);pointers={};directory=bytearray(data[table:table+16*len(rr)])
    for index,text in changes.items():
        if text not in pointers:pointers[text]=len(pool);pool+=text.encode('latin1')+b'\0'
        struct.pack_into('<I',directory,index*16,u32(data,12)+pointers[text])
    # A multiple of 16 keeps the layout calculation and unknown 16-byte marker.
    pool+=bytes((-len(pool))%16);head=bytearray(data[:100]);struct.pack_into('<I',head,8,len(pool))
    out=head+pool+data[table-16:table]+directory;out+=bytes((-len(out))%16);out+=data[base:]
    nr,nt,nb=records(out);assert out[nb:]==data[base:]
    for a,b in zip(rr,nr):assert b['name']==changes.get(a['index'],a['name'])
    return bytes(out)
