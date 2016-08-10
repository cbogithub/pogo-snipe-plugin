# -*- coding: utf-8 -*-
from pokemongo_bot.base_task import BaseTask

class PrintText(BaseTask):
    SUPPORTED_TASK_API_VERSION = 1

    def work(self):
        print 'PrintText!'
        return 'PrintText2'

