"""SOCOM animation-name loader model used to validate the v3.00 resources.

The loader compares each name with previously inserted strings using strcmp;
equal strings are skipped.
Animation Name_Index_Table entries keep their original 16-bit indices.
Different original names must never acquire identical translated bytes.
"""
import struct
from socom_formats import records, u32

def inspect(data,strict=True):
    rr,_,_=records(data);tables=[];active=None;count=0
    for r in rr:
        if r['name']=='Name_Table':
            if not r['children']:active=None;continue
            original=rr[r['index']+1:r['index']+1+r['children']]
            assert all(x['children']==x['size']==0 for x in original)
            names=[];first={};duplicates=[]
            for i,x in enumerate(original):
                if x['name'] in first:duplicates.append(dict(index=i,first=first[x['name']],text=x['name']))
                else:first[x['name']]=i;names.append(x['name'])
            assert original[0]['name']=='NA'
            assert rr[r['index']-1]['name']=='Name_Table_Count'
            assert u32(data,rr[r['index']-1]['offset'])==len(original)
            active=dict(dialog=rr[r['index']-2]['name'],record=r['index'],declared=len(original),loaded=len(names),duplicates=duplicates,index_references=0,shifted_references=0,out_of_range_references=0)
            tables.append(active)
            if strict:assert not duplicates,('Runtime name-table collapse',active)
            active_names=names;original_names=[x['name'] for x in original]
        elif r['name']=='Name_Index_Table' and active is not None:
            assert r['size']%2==0
            for (i,) in struct.iter_unpack('<H',data[r['offset']:r['offset']+r['size']]):
                assert i<len(original_names),(active['dialog'],i,len(original_names))
                active['index_references']+=1;count+=1
                if i>=len(active_names):active['out_of_range_references']+=1
                elif active_names[i]!=original_names[i]:active['shifted_references']+=1
    return dict(tables=tables,table_count=len(tables),index_references=count,
                duplicate_entries=sum(len(t['duplicates']) for t in tables),
                shifted_references=sum(t['shifted_references'] for t in tables),
                out_of_range_references=sum(t['out_of_range_references'] for t in tables))
