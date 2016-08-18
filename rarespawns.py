import re
import requests
from socketIO_client import SocketIO, BaseNamespace

r = requests.get('http://188.165.224.208:49002/api/v1/auth')
auth = r.json()

def rarespawns_noti(data):
  print data


socket = SocketIO(
  host='188.165.224.208',
  port='49001',
  params={'token': auth['token']},
  headers={
    'Referer': 'http://www.rarespawns.be/',
    'Host': '188.165.224.208:49001',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/52.0.2743.116 Safari/537.36',
    'Origin': 'http://www.rarespawns.be',
  }
)
poke_namespace = socket.define(BaseNamespace, '/pokes')
poke_namespace.on('verified', rarespawns_noti)

socket.wait()

