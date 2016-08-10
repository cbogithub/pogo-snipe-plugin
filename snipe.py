# -*- coding: utf-8 -*-
import re
import threading
import time
import base64

from pgoapi.utilities import get_cell_ids

from pokemongo_bot.cell_workers.utils import distance
from pokemongo_bot.worker_result import WorkerResult
from pokemongo_bot.cell_workers.pokemon_catch_worker import PokemonCatchWorker
from pokemongo_bot.base_task import BaseTask
from socketIO_client import SocketIO, BaseNamespace

SNIPE_SLEEP_SEC = 2

class PoGoSnpie(BaseTask):
    SUPPORTED_TASK_API_VERSION = 1

    def initialize(self):
        self.unit = self.bot.config.distance_unit
        self.pokemon_data = self.bot.pokemon_list
        self.watch_pokemon = self.config.get('watch_pokemon', [])
        self.min_ball = self.config.get('min_ball', 1)
        self.pokemon_noti_list = []
        self.pokemon_caught = {}

        self.bot.event_manager.register_event(
            'snipe_teleport_to',
            parameters=('poke_name', 'lat', 'lng')
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
            parameters=('poke_name', 'lat', 'lng')
        )
        self.bot.event_manager.register_event(
            'snipe_not_found',
            parameters=('poke_name', 'lat', 'lng')
        )
        self.bot.event_manager.register_event(
            'snipe_detected',
            parameters=('poke_name', 'lat', 'lng')
        )

        self.sio = SocketIO('188.165.224.208', '49001')
        poke_namespace = self.sio.define(BaseNamespace, '/pokes')
        poke_namespace.on('poke', self.on_poke)
        self.thread = threading.Thread(target=self.process_messages)
        self.thread.start()

    def work(self):
        # check for pokeballs (excluding masterball)
        pokeballs = self.bot.item_inventory_count(1)
        superballs = self.bot.item_inventory_count(2)
        ultraballs = self.bot.item_inventory_count(3)

        if len(self.pokemon_noti_list) == 0:
            return WorkerResult.SUCCESS

        if (pokeballs + superballs + ultraballs) < self.min_ball:
            return WorkerResult.SUCCESS

        pokemon_noti = self.pokemon_noti_list.pop()

        if self.was_caught(pokemon_noti):
            return WorkerResult.SUCCESS

        if pokemon_noti['name'] not in self.watch_pokemon:
            return WorkerResult.SUCCESS

        return self.snipe(pokemon_noti)

    def snipe(self, pokemon_noti):
        self.add_caught(pokemon_noti)
        last_position = self.bot.position[0:2]
        self.bot.heartbeat()

        self._teleport_to(pokemon_noti)
        pokemon = self.find_pokemon(pokemon_noti['lat'], pokemon_noti['lon'], pokemon_noti['name'], True)

        if pokemon == None:
            self._teleport_back(last_position)
            return WorkerResult.SUCCESS

        self._encountered(pokemon)
        catch_worker = PokemonCatchWorker(pokemon, self.bot)
        api_encounter_response = catch_worker.create_encounter_api_call()
        self._teleport_back(last_position)
        self.bot.heartbeat()
        result = catch_worker.work(api_encounter_response)
        return WorkerResult.SUCCESS

    def _teleport_to(self, pokemon_noti):
        self.emit_event(
            'snipe_teleport_to',
            formatted='Teleporting to {poke_name} ({lat} {lng})',
            data={'poke_name': pokemon_noti['name'], 'lat': pokemon_noti['lat'], 'lng': pokemon_noti['lon']}
        )
        self.bot.api.set_position(pokemon_noti['lat'], pokemon_noti['lon'], 0)

    def _encountered(self, pokemon):
        self.emit_event(
            'snipe_encounter',
            formatted='Encountered Pokemon: {poke_name}',
            data={'poke_name': 'pokemon'}
        )

    def _teleport_back(self, last_position):
        self.emit_event(
            'snipe_teleport_back',
            formatted=('Teleporting back to previous location ({last_lat}, '
                       '{last_lon})'),
            data={'last_lat': last_position[0], 'last_lon': last_position[1]}
        )
        time.sleep(SNIPE_SLEEP_SEC)
        self.bot.api.set_position(last_position[0], last_position[1], 0)
        time.sleep(SNIPE_SLEEP_SEC)

    def add_caught(self, pokemon_noti):
        self.pokemon_caught[pokemon_noti['lat'] + pokemon_noti['lon']] = None

    def was_caught(self, pokemon_noti):
        return pokemon_noti['lat'] + pokemon_noti['lon'] in self.pokemon_caught.keys()

    def process_messages(self):
        self.sio.wait()

    def find_pokemon(self, lat, lng, pokemon_name, first_retry):
        self.emit_event(
            'snipe_find_pokemon',
            formatted='Try to find {poke_name} ({lat} {lng}) in 10 seconds',
            data={'poke_name': pokemon_name, 'lat': lat, 'lng': lng}
        )
        time.sleep(10)
        cellid = get_cell_ids(lat, lng)
        timestamp = [0, ] * len(cellid)
        response_dict = self.bot.get_map_objects(lat, lng, timestamp, cellid)
        map_objects = response_dict.get(
            'responses', {}
        ).get('GET_MAP_OBJECTS', {})
        cells = map_objects['map_cells']

        for cell in cells:
            pokemons = []
            if "wild_pokemons" in cell and len(cell["wild_pokemons"]):
                pokemons += cell["wild_pokemons"]
            if "catchable_pokemons" in cell and len(cell["catchable_pokemons"]):
                pokemons += cell["catchable_pokemons"]
            for pokemon in pokemons:
                pokemon = self.get_pokemon(pokemon)
                if pokemon['name'] == pokemon_name:
                    return pokemon

        self.emit_event(
            'snipe_not_found',
            formatted='{poke_name} ({lat} {lng}) is not found',
            data={'poke_name': pokemon_noti['name'], 'lat': pokemon_noti['lat'], 'lng': pokemon_noti['lon']}
        )
        if first_retry == True:
            return self.find_pokemon(lat, lng, pokemon_name, False)
        return None

    def on_poke(self, pokemon_noti):
        p = re.compile(ur'[-]?\d+[.]\d+')
        pokemon_noti['lat'] = float(re.search(p, pokemon_noti['lat']).group())
        pokemon_noti['lon'] = float(re.search(p, pokemon_noti['lon']).group())

        self.emit_event(
            'snipe_detected',
            formatted='{poke_name} ({lat} {lng}) is detected',
            data={'poke_name': pokemon_noti['name'], 'lat': pokemon_noti['lat'], 'lng': pokemon_noti['lon']}
        )

        self.pokemon_noti_list.append(pokemon_noti)

    def get_pokemon(self, pokemon):
        print pokemon
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