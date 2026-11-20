"""Versioned lossless JSON-row blocks. Integrity/bounds, never owner authority."""
import struct,zlib,hashlib
MAGIC=b'RZ1\0'
MAX_ROWS=256
MAX_EXPANDED=1047552
MAX_OPERATION_EXPANDED=3221225472

def encode_block(rows):
    if type(rows) is not tuple or not 1<=len(rows)<=MAX_ROWS or any(type(x) is not bytes or not 0<len(x)<=1048576 for x in rows):
        raise ValueError('bounded exact canonical row bytes required')
    raw=b''.join(b'R'+struct.pack('>I',len(x))+x for x in rows)
    if len(raw)>MAX_EXPANDED:raise ValueError('expanded block bound')
    payload=MAGIC+struct.pack('>II',len(rows),len(raw))+hashlib.sha256(raw).digest()+zlib.compress(raw,6)
    if len(payload)>1048576:raise ValueError('compressed physical frame bound')
    return payload

def block_count(payload):
    if type(payload) is not bytes or not 44<len(payload)<=1048576 or payload[:4]!=MAGIC:raise ValueError('versioned complete block required')
    count,size=struct.unpack_from('>II',payload,4)
    if not 1<=count<=MAX_ROWS or not 0<size<=MAX_EXPANDED:raise ValueError('block declaration bounds')
    return count

def decode_block(payload):
    count=block_count(payload);size=struct.unpack_from('>I',payload,8)[0]
    d=zlib.decompressobj();raw=d.decompress(payload[44:],MAX_EXPANDED+1)
    if len(raw)!=size or not d.eof or d.unused_data or d.unconsumed_tail or hashlib.sha256(raw).digest()!=payload[12:44]:
        raise ValueError('truncated/trailing/expanded/hash-mismatched block')
    rows=[];offset=0
    while offset<len(raw):
        if offset+5>len(raw) or raw[offset:offset+1]!=b'R':raise ValueError('exact row framing')
        n=struct.unpack_from('>I',raw,offset+1)[0];offset+=5
        if not 0<n<=1048576 or offset+n>len(raw):raise ValueError('row bounds')
        rows.append(raw[offset:offset+n]);offset+=n
        if len(rows)>count:raise ValueError('row expansion count')
    if len(rows)!=count:raise ValueError('missing/extra rows')
    return tuple(rows)


class EncodedRows:
    """Fresh bounded decode per iteration over the SAME immutable capture.

    Data integrity only: this object grants no owner/admission authority and
    performs no filesystem or transport read. Both semantic passes run in full.
    """
    __slots__=('_raw','_count','_limit')
    def __init__(self,raw,count,limit):
        if type(raw) is bytes:
            view=memoryview(raw)
        elif (type(raw) is memoryview and raw.readonly and type(raw.obj) is bytes
              and raw.ndim==1 and raw.format=='B' and raw.c_contiguous):
            view=raw
        else:raise ValueError('immutable byte capture required')
        if (len(view)>402653184 or type(count) is not int or type(limit) is not int
                or not 0<=count<=limit<=700000):raise ValueError('bounded complete row count required')
        object.__setattr__(self,'_raw',view);object.__setattr__(self,'_count',count);object.__setattr__(self,'_limit',limit)
    def __setattr__(self,name,value):raise AttributeError('immutable encoded row view')
    def __len__(self):return self._count
    def __iter__(self):
        import json,time
        def pairs(items):
            out={}
            for key,value in items:
                if key in out:raise ValueError('duplicate JSON key')
                out[key]=value
            return out
        def nonfinite(value):raise ValueError('nonfinite JSON constant:'+value)
        o=0;seen=0;expanded=0;raw=self._raw
        while o<len(raw):
            if o+5>len(raw):raise ValueError('truncated encoded row header')
            tag=bytes(raw[o:o+1]);n=struct.unpack_from('>I',raw,o+1)[0];o+=5
            if not 0<n<=1048576 or o+n>len(raw):raise ValueError('encoded row frame bounds')
            payload=bytes(raw[o:o+n]);o+=n
            if tag==b'Z':blocks=decode_block(payload)
            elif tag==b'R':blocks=(payload,)
            else:raise ValueError('only exact captured row frames accepted')
            expanded+=sum(len(b)+5 for b in blocks)
            if expanded>MAX_OPERATION_EXPANDED:raise ValueError('encoded row expansion budget')
            for block in blocks:
                seen+=1
                if seen>self._count or seen>self._limit:raise ValueError('extra encoded rows')
                value=json.loads(block,object_pairs_hook=pairs,parse_constant=nonfinite)
                if json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()!=block:
                    raise ValueError('noncanonical captured row')
                yield value
            # Bounded cooperation, not a timestamp refresh or a guard bypass.
            time.sleep(0)
        if seen!=self._count:raise ValueError('missing encoded rows')
