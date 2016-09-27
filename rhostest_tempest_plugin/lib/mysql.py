# Copyright 2016
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import pymysql

from tempest import config


CONF = config.CONF


class Client(object):

    def __init__(self, dbconf=CONF):
        self.db_config = {
            "username": dbconf.whitebox_plugin.nova_db_username,
            "password": dbconf.whitebox_plugin.nova_db_password,
            "host": dbconf.whitebox_plugin.nova_db_hostname,
            "database": dbconf.whitebox_plugin.nova_db_database,
        }

    def connect(self):
        return pymysql.connect(
            self.db_config['host'],
            self.db_config['username'],
            self.db_config['password'],
            self.db_config['database'],
        )

default_client = Client()
