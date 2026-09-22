"""Model SOCOM's in-place RDR pointer relocation and reverse relocation.

The load and unload routines visit children without a visited-node set. Sharing a list that
contains pointer entries relocates those entries twice. Scalar-only leaves
are safe because neither routine writes their headers or scalar values.
"""
import struct

def runtime_roundtrip(data,start,size):
    original=bytes(data[start:start+size]);b=bytearray(original)
    pool_len,tree=struct.unpack_from('<II',b)
    address=0x01000000;pool_base=address+8;tree_base=address+tree
    writes=set();visits=0
    def node(pos,relocate,depth=0):
        nonlocal visits
        assert depth<100 and tree<=pos<=size-8,('Invalid list address',pos)
        kind,count=struct.unpack_from('<II',b,pos)
        assert kind==1 and 1<=count and pos+8*count<=size,('Invalid list header',pos,kind,count)
        visits+=1
        for i in range(1,count):
            off=pos+i*8;tag,v=struct.unpack_from('<II',b,off)
            assert tag in (1,2,3,4),(off,tag)
            if tag in (1,2):continue
            if relocate:
                assert off not in writes,('Pointer entry visited twice',off,tag)
                writes.add(off)
                if tag==3:
                    assert v<pool_len and b.find(0,8+v,8+pool_len)!=-1,('Invalid string offset',off,v)
                    struct.pack_into('<I',b,off+4,v+pool_base)
                else:
                    struct.pack_into('<I',b,off+4,v+tree_base)
                    node(tree+v,True,depth+1)
            elif tag==3:
                assert pool_base<=v<pool_base+pool_len
                struct.pack_into('<I',b,off+4,v-pool_base)
            else:
                assert tree_base<=v<address+size
                node(v-address,False,depth+1)
                struct.pack_into('<I',b,off+4,v-tree_base)
    node(tree,True)
    loaded_visits=visits
    node(tree,False)
    assert bytes(b)==original,'Runtime load/unload did not restore original bytes'
    return {'node_visits':loaded_visits,'pointer_entries':len(writes),'load_unload':'passed'}
