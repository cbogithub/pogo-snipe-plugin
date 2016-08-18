import re
from socketIO_client import SocketIO, BaseNamespace

def pokezz_noti(data):
  p = re.compile(ur'(\d+)\|([-]?\d+.\d+)\|([-]?\d+.\d+)\|(\d+)\|(\d)')
  m = re.findall(p, data)[0]

  print m

socket = SocketIO(
  host='https://pokezz.com',
  verify=False,
  Namespace=BaseNamespace,
  headers={
    'Referer': 'https://pokezz.com/',
    'Host': 'pokezz.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36',
    'Origin': 'https://pokezz.com',
  }
)

socket.on('b', pokezz_noti)

socket.wait()

