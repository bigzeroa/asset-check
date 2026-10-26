"""Create a new fictional asset folder; never scan or overwrite personal files."""
from pathlib import Path
from PIL import Image
P=Path(__file__).parent/'demo';P.mkdir(exist_ok=False)
Image.new('RGBA',(64,64),(20,180,150,255)).save(P/'hero.png')
(P/'hero-copy.png').write_bytes((P/'hero.png').read_bytes())
Image.new('RGB',(32,32),(230,130,50)).save(P/'actually-jpeg.png',format='JPEG')
Image.new('RGBA',(512,64),(50,100,200,255)).save(P/'wide-texture.png')
(P/'broken.png').write_bytes(b'This is a fictional invalid image, not a real PNG.')
print(P)
