# -*- coding: utf-8 -*-
from pokemongo_bot.base_task import BaseTask

class PrintText(BaseTask):
    SUPPORTED_TASK_API_VERSION = 1

    def initialize(self):
        self.watch_pokemon = self.bot.watch_pokemon
        self.watch_iv = self.bot.watch_iv

    def work(self):
        print sef.watch_pokemon
        print sef.watch_iv
        return 'PrintText2'

