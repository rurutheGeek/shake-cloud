"""Generate a one-second PCM16 BCSTM fixture, without third-party media."""
import math,struct,sys
from pathlib import Path
rate=8000
pcm=b''.join(struct.pack('<h',int(1000*math.sin(i*2*math.pi*440/rate))) for i in range(rate))
header=bytearray(64);header[:4]=b'CSTM'
struct.pack_into('<HHIIHH',header,4,0xfeff,64,0x00030000,64+96+8+len(pcm),2,0)
struct.pack_into('<HHII',header,20,0x4000,0,64,96)
struct.pack_into('<HHII',header,32,0x4002,0,160,8+len(pcm))
info=bytearray(96);info[:4]=b'INFO';struct.pack_into('<I',info,4,96);struct.pack_into('<I',info,12,24)
struct.pack_into('<BBBBIIIIIIIII',info,32,1,0,1,0,rate,0,rate,1,len(pcm),rate,len(pcm),rate,len(pcm))
Path(sys.argv[1]).write_bytes(header+info+b'DATA'+struct.pack('<I',8+len(pcm))+pcm)
