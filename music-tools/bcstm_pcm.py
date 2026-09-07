"""Decode BCSTM PCM blocks to WAV, avoiding FFmpeg's ADPCM last-block trim on PCM."""
import struct,wave
from pathlib import Path

def decode_pcm(source,output):
 with open(source,'rb') as src:
  header=src.read(20)
  if len(header)!=20 or header[:4] not in (b'CSTM',b'FSTM'):return False
  endian='<' if header[4:6]==b'\xff\xfe' else '>' if header[4:6]==b'\xfe\xff' else None
  if endian is None:raise ValueError('Invalid BCSTM byte order')
  unpack=lambda fmt,b:struct.unpack(endian+fmt,b)
  sections=unpack('H',header[16:18])[0]
  if sections>64:raise ValueError('Invalid BCSTM section count')
  info=data=None
  for _ in range(sections):
   flag,_,offset,size=unpack('HHII',src.read(12))
   if flag==0x4000:info=offset
   if flag==0x4002:data=offset+8
  if info is None or data is None:raise ValueError('Missing BCSTM INFO/DATA')
  src.seek(info+12);relative=unpack('I',src.read(4))[0];src.seek(info+8+relative)
  codec,loop,channels,_=src.read(4)
  if codec not in (0,1):return False
  rate,loop_start,total,blocks,block_bytes,block_samples,last_bytes,last_samples,last_padded=unpack('9I',src.read(36))
  width=codec+1
  if not (1<=channels<=16 and 1<=rate<=384000 and 1<=blocks<=65535 and total<=rate*21600):raise ValueError('Invalid BCSTM PCM parameters')
  if total!=(blocks-1)*block_samples+last_samples:raise ValueError('Inconsistent BCSTM sample count')
  if block_bytes<block_samples*width or last_bytes<last_samples*width or last_padded<last_bytes:raise ValueError('Invalid BCSTM block sizes')
  if data+(blocks-1)*block_bytes*channels+last_padded*channels>Path(source).stat().st_size:raise ValueError('Truncated BCSTM')
  src.seek(data)
  with wave.open(str(output),'wb') as wav:
   wav.setnchannels(channels);wav.setsampwidth(width);wav.setframerate(rate)
   for i in range(blocks):
    samples=last_samples if i==blocks-1 else block_samples
    stride=last_padded if i==blocks-1 else block_bytes
    if samples*channels*width>64*1024*1024:raise ValueError('BCSTM block too large')
    planes=[]
    for _ in range(channels):
     raw=src.read(samples*width);src.seek(stride-len(raw),1)
     if len(raw)!=samples*width:raise ValueError('Truncated PCM')
     if width==1:raw=bytes(v^128 for v in raw)
     elif endian=='>':raw=b''.join(raw[j:j+2][::-1] for j in range(0,len(raw),2))
     planes.append(raw)
    if channels==1:wav.writeframesraw(planes[0])
    else:wav.writeframesraw(b''.join(channel[j:j+width] for j in range(0,samples*width,width) for channel in planes))
 return True
