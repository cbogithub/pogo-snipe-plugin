# -*- coding: utf-8 -*-
import re
import time
import base64
import requests
import Queue
import threading

from pgoapi.utilities import get_cell_ids
from sets import Set
from pokemongo_bot.cell_workers.utils import distance
from pokemongo_bot.worker_result import WorkerResult
from pokemongo_bot.cell_workers.pokemon_catch_worker import PokemonCatchWorker
from pokemongo_bot.base_task import BaseTask
from socketIO_client import SocketIO, BaseNamespace

SNIPE_SLEEP_SEC = 2
GET_MAP_OBJECT_SLEEP_SEC = 10

class SnipeInfo(object):
  def __init__(self, data):
    self._data = data
    self.id = str(data['latitude']) + str(data['longitude'])
    self.pokemon_name = data['pokemon_name']
    self.latitude = data['latitude']
    self.longitude = data['longitude']
    self.expired = data['expired']

class PoGoSnpie(BaseTask):
  SUPPORTED_TASK_API_VERSION = 1

  def initialize(self):
    self.pokemon_caught = Set()
    self.pokemon_wait_snipe = Set()
    self.wait_snipe_queue = Queue.Queue()
    self.pokemon_data = self.bot.pokemon_list

    self.watch_pokemon = self.config.get('watch_pokemon', [])
    self.min_ball = self.config.get('min_ball', 1)
    self.run_pokezz = self.config.get('pokezz', False)
    self.run_rarespawns = self.config.get('rarespawns', False)

    self.bot.event_manager.register_event(
      'snipe_teleport_to',
      parameters=('poke_name', 'lat', 'lon')
    )
    self.bot.event_manager.register_event(
      'snipe_encounter',
      parameters=('poke_name')
    )
    self.bot.event_manager.register_event(
      'snipe_teleport_back',
      parameters=('last_lat', 'last_lon')
    )
    self.bot.event_manager.register_event(
      'snipe_find_pokemon',
      parameters=('poke_name', 'lat', 'lon')
    )
    self.bot.event_manager.register_event(
      'snipe_not_found',
      parameters=('poke_name', 'lat', 'lon')
    )
    self.bot.event_manager.register_event(
      'snipe_detected',
      parameters=('poke_name', 'lat', 'lon', 'source')
    )

    if self.run_pokezz:
      self.pokezz()
    if self.run_rarespawns:
      self.rarespawns()

  def pokezz(self):
    self.pokezz_sock = SocketIO(
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
    self.pokezz_sock.on('b', self.pokezz_noti)
    self.pokezz_thread = threading.Thread(target=self.pokezz_thread_process)
    self.pokezz_thread.start()

  def pokezz_thread_process(self):
    self.pokezz_sock.wait()

  def pokezz_noti(self, data):
    p = re.compile(ur'(\d+)\|([-]?\d+.\d+)\|([-]?\d+.\d+)\|(\d+)\|(\d)')
    m = re.findall(p, data)[0]

    if m[4] != '1':
      return

    s = SnipeInfo({
      'pokemon_name': self.bot.pokemon_list[int(m[0]) - 1]['Name'],
      'latitude': float(m[1]),
      'longitude': float(m[2]),
      'expired': int(m[3]),
    })

    self.add_queue(s, 'pokezz')

  def rarespawns(self):
    r = requests.get('http://188.165.224.208:49002/api/v1/auth')
    auth = r.json()

    self.rarespawns_sock = SocketIO(
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
    poke_namespace = self.rarespawns_sock.define(BaseNamespace, '/pokes')
    poke_namespace.on('verified', self.rarespawns_noti)
    self.pokezz_thread = threading.Thread(target=self.rarespawns_thread_process)
    self.pokezz_thread.start()

  def rarespawns_thread_process(self):
    self.rarespawns_sock.wait()

  def rarespawns_noti(self, data):
    p = re.compile(ur'[-]?\d+[.]\d+')
    lat = re.search(p, data['lat']).group()
    lon = re.search(p, data['lon']).group()

    s = SnipeInfo({
      'pokemon_name': data['name'],
      'latitude': float(lat),
      'longitude': float(lon),
      'expired': time.time() + 120,
    })

    self.add_queue(s, 'rarespawns')

  def add_queue(self, snipe_info, source):
    if snipe_info.id in self.pokemon_wait_snipe:
      return
    if snipe_info.id in self.pokemon_caught:
      return
    if len(self.watch_pokemon) > 0 and snipe_info.pokemon_name not in self.watch_pokemon:
      return

    self.pokemon_wait_snipe.add(snipe_info.id)
    self.wait_snipe_queue.put(snipe_info)

    self.emit_event(
      'snipe_detected',
      formatted='{poke_name} {lat}, {lon} is detected from {source}',
      data={'poke_name': snipe_info.pokemon_name, 'lat': snipe_info.latitude, 'lon': snipe_info.longitude, 'source': source}
    )

  def work(self):
    if self.wait_snipe_queue.qsize < 1:
      return WorkerResult.SUCCESS

    try:
      while True:
        superballs = self.bot.item_inventory_count(2)
        ultraballs = self.bot.item_inventory_count(3)
        if (superballs + ultraballs) < self.min_ball:
          return WorkerResult.SUCCESS

        snipe_info = self.wait_snipe_queue.get_nowait()

        if snipe_info.expired - time.time() < 30:
          self.wait_snipe_queue.task_done()
          continue

        self.snipe(snipe_info)
        self.wait_snipe_queue.task_done()
    except Queue.Empty:
      self.pokemon_caught.clear()
      return WorkerResult.SUCCESS

  def snipe(self, snipe_info):
    self.pokemon_caught.add(snipe_info.id)
    self.pokemon_wait_snipe.discard(snipe_info.id)

    last_position = self.bot.position[0:2]
    self.bot.heartbeat()

    self._teleport_to(snipe_info)
    pokemon = self.find_pokemon(snipe_info, True)

    if pokemon == None:
      self._teleport_back(last_position)
      return

    self._encountered(pokemon)
    catch_worker = PokemonCatchWorker(pokemon, self.bot, self.config)
    api_encounter_response = catch_worker.create_encounter_api_call()
    self._teleport_back(last_position)
    self.bot.heartbeat()
    catch_worker.work(api_encounter_response)

  def _teleport_to(self, snipe_info):
    self.emit_event(
      'snipe_teleport_to',
      formatted='Teleporting to {poke_name} {lat}, {lon}',
      data={'poke_name': snipe_info.pokemon_name, 'lat': snipe_info.latitude, 'lon': snipe_info.longitude}
    )
    self.bot.api.set_position(snipe_info.latitude, snipe_info.longitude, 0)

  def _teleport_back(self, last_position):
    self.emit_event(
      'snipe_teleport_back',
      formatted=('Teleporting back to previous location {last_lat}, {last_lon}'),
        data={'last_lat': last_position[0], 'last_lon': last_position[1]}
    )
    time.sleep(SNIPE_SLEEP_SEC)
    self.bot.api.set_position(last_position[0], last_position[1], 0)
    time.sleep(SNIPE_SLEEP_SEC)

  def _encountered(self, pokemon):
    self.emit_event(
      'snipe_encounter',
      formatted='Encountered Pokemon: {poke_name}',
      data={'poke_name': pokemon['name']}
    )

  def find_pokemon(self, snipe_info, first_retry):
    self.emit_event(
      'snipe_find_pokemon',
      formatted='Try to find {poke_name} {lat}, {lon} in 10 seconds',
      data={'poke_name': snipe_info.pokemon_name, 'lat': snipe_info.latitude, 'lon': snipe_info.longitude}
    )
    time.sleep(GET_MAP_OBJECT_SLEEP_SEC)
    cellid = get_cell_ids(snipe_info.latitude, snipe_info.longitude)
    timestamp = [0, ] * len(cellid)
    response_dict = self.bot.get_map_objects(snipe_info.latitude, snipe_info.longitude, timestamp, cellid)
    map_objects = response_dict.get('responses', {}).get('GET_MAP_OBJECTS', {})
    cells = map_objects['map_cells']

    for cell in cells:
        pokemons = []
        if "wild_pokemons" in cell and len(cell["wild_pokemons"]):
            pokemons += cell["wild_pokemons"]
        if "catchable_pokemons" in cell and len(cell["catchable_pokemons"]):
            pokemons += cell["catchable_pokemons"]
        for pokemon in pokemons:
            pokemon = self.get_pokemon(pokemon)
            if pokemon['name'] == snipe_info.pokemon_name:
                return pokemon

    self.emit_event(
        'snipe_not_found',
        formatted='{poke_name} ({lat} {lon}) is not found',
        data={'poke_name': snipe_info.pokemon_name, 'lat': snipe_info.latitude, 'lon': snipe_info.longitude}
    )
    if first_retry == True:
        return self.find_pokemon(snipe_info, False)
    return None

  def get_pokemon(self, pokemon):
    if 'pokemon_id' not in pokemon:
      pokemon['pokemon_id'] = pokemon['pokemon_data']['pokemon_id']

    if 'time_till_hidden_ms' not in pokemon:
      pokemon['time_till_hidden_ms'] = pokemon['expiration_timestamp_ms']

    pokemon['disappear_time'] = int(pokemon['time_till_hidden_ms'] / 1000)
    pokemon['name'] = self.pokemon_data[pokemon['pokemon_id'] - 1]['Name']
    pokemon['is_vip'] = pokemon['name'] in self.bot.config.vips
    pokemon['dist'] = distance(
      self.bot.position[0],
      self.bot.position[1],
      pokemon['latitude'],
      pokemon['longitude'],
    )

    return pokemon

