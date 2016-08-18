from socketIO_client import SocketIO, BaseNamespace

def pokezz_noti(data):
  print data

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

