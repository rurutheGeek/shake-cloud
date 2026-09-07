import importlib.util,struct,tempfile,unittest,wave
from pathlib import Path
spec=importlib.util.spec_from_file_location('bcstm_pcm',Path(__file__).resolve().parents[1]/'music-tools/bcstm_pcm.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class BcstmPcmTest(unittest.TestCase):
 def fixture(self,endian,codec):
  width=codec+1;channels=2;counts=[4,3];data=b'';expected=b''
  for block,count in enumerate(counts):
   planes=[]
   for channel in range(channels):
    samples=[block*20+channel*10+i-30 for i in range(count)]
    planes.append(samples)
    data+=b''.join(struct.pack(endian+('h' if width==2 else 'b'),x) for x in samples)
    data+=b'\0'*(4*width-count*width)
   for i in range(count):
    for plane in planes:expected+=struct.pack('<h',plane[i]) if width==2 else bytes([plane[i]+128])
  header=bytearray(64);header[:4]=b'CSTM';struct.pack_into(endian+'HHIIHH',header,4,0xfeff,64,0x30000,168+len(data),2,0)
  struct.pack_into(endian+'HHII',header,20,0x4000,0,64,96);struct.pack_into(endian+'HHII',header,32,0x4002,0,160,8+len(data))
  info=bytearray(96);info[:4]=b'INFO';struct.pack_into(endian+'I',info,4,96);struct.pack_into(endian+'I',info,12,24)
  struct.pack_into(endian+'BBBB9I',info,32,codec,0,channels,0,8000,0,7,2,4*width,4,3*width,3,4*width)
  return bytes(header+info+b'DATA'+struct.pack(endian+'I',8+len(data))+data),expected
 def test_pcm_variants_preserve_last_block_and_channels(self):
  for endian in ['<','>']:
   for codec in [0,1]:
    with self.subTest(endian=endian,codec=codec),tempfile.TemporaryDirectory() as d:
     raw,expected=self.fixture(endian,codec);src=Path(d)/'in.bcstm';out=Path(d)/'out.wav';src.write_bytes(raw)
     self.assertTrue(module.decode_pcm(src,out));self.assertEqual(src.read_bytes(),raw)
     with wave.open(str(out)) as w:self.assertEqual(w.getnframes(),7);self.assertEqual(w.readframes(7),expected)
 def test_truncated_file_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   raw,_=self.fixture('<',1);src=Path(d)/'in.bcstm';src.write_bytes(raw[:-1])
   with self.assertRaises(ValueError):module.decode_pcm(src,Path(d)/'out.wav')
